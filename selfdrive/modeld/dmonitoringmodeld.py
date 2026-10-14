#!/usr/bin/env python3
import base64
import os
import pickle
import time
from pathlib import Path

import numpy as np

from openpilot.system.hardware import TICI

os.environ["DEV"] = "QCOM" if TICI else "CPU"

from tinygrad.tensor import Tensor

from cereal import messaging
from cereal.messaging import PubMaster, SubMaster
from msgq.visionipc import VisionBuf, VisionIpcClient, VisionStreamType
from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.common.transformations.camera import _ar_ox_fisheye, _os_fisheye
from openpilot.common.transformations.model import dmonitoringmodel_intrinsics
from openpilot.selfdrive.modeld.helpers import load_precompiled_artifact
from openpilot.selfdrive.modeld.parse_model_outputs import safe_exp, sigmoid
from openpilot.starpilot.common.model_lab import load_model_lab_config
from openpilot.system.hardware.usb import chestnut_firmware_ready
from openpilot.system.camerad.cameras.nv12_info import get_nv12_info

PROCESS_NAME = "selfdrive.modeld.dmonitoringmodeld"
SEND_RAW_PRED = os.getenv("SEND_RAW_PRED")
MODELS_DIR = Path(__file__).parent / "models"
MODEL_PKL_PATH = MODELS_DIR / "dmonitoring_model_tinygrad.pkl"
DEFAULT_DMONITORING_CORES = 7
MODEL_LAB_DMONITORING_CORES = [0, 1, 2, 3]


def dmonitoring_cpu_cores(params: Params, chestnut_ready: bool) -> int | list[int]:
  if chestnut_ready and load_model_lab_config(params)["enabled"]:
    return MODEL_LAB_DMONITORING_CORES
  return DEFAULT_DMONITORING_CORES


class ModelState:
  def __init__(self, cam_w: int, cam_h: int):
    # tinygrad d3f09c9b artifact from examples/openpilot/compile_onnx.py (comma's DM path at d05c2d971b): a dict with the
    # JIT, its input/output specs and the ONNX metadata (output_slices); the warp is a compile_warp.py dict.
    jits = load_precompiled_artifact(MODEL_PKL_PATH)
    self.device = jits["input_specs"]["input_img"][2]
    self.input_shapes = jits["metadata"]["input_shapes"]
    self.output_slices = pickle.loads(base64.b64decode(jits["metadata"]["metadata"]["output_slices"]))

    self.numpy_inputs = {"calib": np.zeros(self.input_shapes["calib"], dtype=np.float32)}
    self.warp_numpy_inputs = {"transform": np.zeros((3, 3), dtype=np.float32)}
    self.warp_inputs = {key: Tensor(value, device="NPY") for key, value in self.warp_numpy_inputs.items()}
    self.frame_size = get_nv12_info(cam_w, cam_h)[3]
    self.tensor_inputs = {key: Tensor(value, device=self.device).realize() for key, value in self.numpy_inputs.items()}
    self.calib_host = Tensor(self.numpy_inputs["calib"], device="NPY")._buffer()
    self._blob_cache: dict[int, Tensor] = {}
    self.model_run = jits["run"]
    self.outputs = {name: Tensor(np.zeros(shape, dtype=dtype), device=device).realize()
                    for name, (shape, dtype, device) in jits["output_specs"].items()}
    with open(MODELS_DIR / f"dm_warp_{cam_w}x{cam_h}_tinygrad.pkl", "rb") as warp_file:
      self.image_warp = pickle.load(warp_file)["run"]

  def run(self, buf: VisionBuf, calib: np.ndarray, transform: np.ndarray) -> tuple[np.ndarray, float]:
    self.numpy_inputs["calib"][0, :] = calib
    start = time.perf_counter()
    self.tensor_inputs["calib"]._buffer().copy_from(self.calib_host)

    ptr = np.frombuffer(buf.data, dtype=np.uint8).ctypes.data
    # camerad's buffers are a ring: cache one tensor per buffer
    if ptr not in self._blob_cache:
      self._blob_cache[ptr] = Tensor.from_blob(ptr, (self.frame_size,), dtype="uint8", device=self.device)

    self.warp_numpy_inputs["transform"][:] = transform
    self.tensor_inputs["input_img"] = self.image_warp(input_frame=self._blob_cache[ptr], M_inv=self.warp_inputs["transform"])
    self.model_run(output_buffers=self.outputs, **self.tensor_inputs)
    output = self.outputs["outputs"].numpy().astype(np.float32).reshape(-1)
    return output, time.perf_counter() - start


def slice_outputs(model_outputs, output_slices):
  return {key: model_outputs[np.newaxis, value] for key, value in output_slices.items()}


def parse_model_output(model_output):
  parsed = {"wheel_on_right": sigmoid(model_output["wheel_on_right"])}
  for suffix in ("lhd", "rhd"):
    face_descs = model_output[f"face_descs_{suffix}"]
    parsed[f"face_descs_{suffix}"] = face_descs[:, :-6]
    parsed[f"face_descs_{suffix}_std"] = safe_exp(face_descs[:, -6:])
    for key in (
      "face_prob",
      "left_eye_prob",
      "right_eye_prob",
      "left_blink_prob",
      "right_blink_prob",
      "sunglasses_prob",
      "using_phone_prob",
    ):
      parsed[f"{key}_{suffix}"] = sigmoid(model_output[f"{key}_{suffix}"])
    sleep_key = f"sleep_prob_{suffix}"
    parsed[sleep_key] = (
      sigmoid(model_output[sleep_key])
      if sleep_key in model_output
      else np.zeros((1, 1), dtype=np.float32)
    )
  return parsed


def fill_driver_data(msg, model_output, suffix):
  msg.faceOrientation = model_output[f"face_descs_{suffix}"][0, :3].tolist()
  msg.faceOrientationStd = model_output[f"face_descs_{suffix}_std"][0, :3].tolist()
  msg.facePosition = model_output[f"face_descs_{suffix}"][0, 3:5].tolist()
  msg.facePositionStd = model_output[f"face_descs_{suffix}_std"][0, 3:5].tolist()
  msg.faceProb = model_output[f"face_prob_{suffix}"][0, 0].item()
  msg.leftEyeProb = model_output[f"left_eye_prob_{suffix}"][0, 0].item()
  msg.rightEyeProb = model_output[f"right_eye_prob_{suffix}"][0, 0].item()
  msg.leftBlinkProb = model_output[f"left_blink_prob_{suffix}"][0, 0].item()
  msg.rightBlinkProb = model_output[f"right_blink_prob_{suffix}"][0, 0].item()
  msg.sunglassesProb = model_output[f"sunglasses_prob_{suffix}"][0, 0].item()
  msg.phoneProb = model_output[f"using_phone_prob_{suffix}"][0, 0].item()
  msg.sleepProb = model_output[f"sleep_prob_{suffix}"][0, 0].item()


def get_driverstate_packet(model_output, frame_id: int, exec_time: float, gpu_exec_time: float):
  msg = messaging.new_message("driverStateV2", valid=True)
  state = msg.driverStateV2
  state.frameId = frame_id
  state.modelExecutionTime = exec_time
  state.gpuExecutionTime = gpu_exec_time
  state.rawPredictions = model_output["raw_pred"]
  state.wheelOnRightProb = model_output["wheel_on_right"][0, 0].item()
  fill_driver_data(state.leftDriverData, model_output, "lhd")
  fill_driver_data(state.rightDriverData, model_output, "rhd")
  return msg


def main():
  params = Params()
  cpu_cores = dmonitoring_cpu_cores(params, chestnut_firmware_ready())
  config_realtime_process(cpu_cores, 5)
  cloudlog.info(f"driver monitoring CPU affinity: {cpu_cores}")
  cloudlog.warning("connecting to driver stream")
  vipc_client = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_DRIVER, True)
  while not vipc_client.connect(False):
    time.sleep(0.1)
  assert vipc_client.is_connected()
  cloudlog.warning(f"connected with buffer size: {vipc_client.buffer_len}")

  # connect() finishes before stream is populated. The first buffer always has known dimensions.
  first_buf = vipc_client.recv()
  while first_buf is None:
    first_buf = vipc_client.recv()

  model = ModelState(first_buf.width, first_buf.height)
  cloudlog.warning("models loaded, dmonitoringmodeld starting")

  sm = SubMaster(["liveCalibration"])
  pm = PubMaster(["driverStateV2"])
  calib = np.zeros(model.numpy_inputs["calib"].size, dtype=np.float32)
  model_transform = None

  while True:
    buf = vipc_client.recv()
    if buf is None:
      continue

    if model_transform is None:
      camera = _os_fisheye if buf.width == _os_fisheye.width else _ar_ox_fisheye
      model_transform = np.linalg.inv(
        np.dot(dmonitoringmodel_intrinsics, np.linalg.inv(camera.intrinsics)),
      ).astype(np.float32)

    sm.update(0)
    if sm.updated["liveCalibration"]:
      calib[:] = np.array(sm["liveCalibration"].rpyCalib)

    start = time.perf_counter()
    model_output, gpu_execution_time = model.run(buf, calib, model_transform)
    execution_time = time.perf_counter() - start
    raw_pred = model_output.tobytes() if SEND_RAW_PRED else b""
    parsed = parse_model_output(slice_outputs(model_output, model.output_slices))
    parsed["raw_pred"] = raw_pred
    pm.send(
      "driverStateV2",
      get_driverstate_packet(parsed, vipc_client.frame_id, execution_time, gpu_execution_time),
    )


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    cloudlog.warning("got SIGINT")
