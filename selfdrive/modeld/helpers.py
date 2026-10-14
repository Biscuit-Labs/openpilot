import io
import json
import os
import pickle
import pickletools
import shutil
import struct
import tempfile
from pathlib import Path

from tinygrad.device import Buffer, Device
from openpilot.system.hardware.usb import chestnut_firmware_ready

MODELS_DIR = Path(__file__).resolve().parent / "models"
TG_INPUT_DEVICES_PATH = MODELS_DIR / "tg_input_devices.json"
USBGPU_VID = 0xADD1
USBGPU_PID = 0x0001


def _default_tinygrad_backend() -> str:
  env_dev = os.getenv("DEV", "").strip()
  if env_dev:
    default_target = env_dev.split(";", 1)[0]
    return default_target.split(":", 1)[0].split("+", 1)[-1] or default_target

  try:
    default = Device.DEFAULT
  except Exception:
    default = ""

  if isinstance(default, str) and default:
    return default.split(":", 1)[0].split("+", 1)[-1] or default
  return "QCOM" if Path("/dev/kgsl-3d0").exists() else "CPU"


def _load_tg_devices() -> dict:
  if not TG_INPUT_DEVICES_PATH.is_file():
    return {}
  with open(TG_INPUT_DEVICES_PATH) as f:
    return json.load(f)


def _fallback_tg_devices(process_name: str, usbgpu: bool) -> dict[str, str]:
  backend = _default_tinygrad_backend()
  if process_name == "selfdrive.modeld.dmonitoringmodeld":
    return {"DEV": backend}

  # The external-GPU profile is only selected after Chestnut has been
  # recognized. Match upstream's generated device map and select AMD directly;
  # probing every tinygrad backend opens CL/DSP/CPU devices inside modeld and
  # can interfere with the on-road QCOM + AMD process.
  return {"WARP_DEV": backend, "QUEUE_DEV": "AMD" if usbgpu else backend}


def get_tg_input_devices(process_name: str, usbgpu: bool) -> dict[str, str]:
  tg_devices = _load_tg_devices()
  process_devices = tg_devices.get(process_name, {})
  profile = "usbgpu" if usbgpu else "default"
  if profile in process_devices:
    return process_devices[profile]
  return _fallback_tg_devices(process_name, usbgpu)


def modeld_pkl_path(usbgpu: bool) -> Path:
  prefix = "big_" if usbgpu else ""
  return MODELS_DIR / f"{prefix}driving_tinygrad.pkl"


def usbgpu_present() -> bool:
  return chestnut_firmware_ready()


def tinygrad_dev_config(usbgpu: bool, tici: bool) -> str:
  default = "QCOM" if tici else ("CPU:LLVM" if usbgpu else "LLVM")
  return f"{default};USB+AMD:LLVM" if usbgpu else default


def dump_oob(obj, output) -> None:
  """Pickle large buffers out-of-band so model weights are never duplicated in RAM."""
  with tempfile.TemporaryFile(dir=".") as buffers:
    def buffer_callback(pickle_buffer: pickle.PickleBuffer):
      view = pickle_buffer.raw()
      buffers.write(struct.pack("<q", view.nbytes))
      buffers.write(view)
      pickle_buffer.release()

    opcodes = io.BytesIO()
    pickle.Pickler(opcodes, protocol=5, buffer_callback=buffer_callback).dump(obj)
    opcode_data = opcodes.getvalue()
    output.write(struct.pack("<q", len(opcode_data)))
    output.write(opcode_data)
    buffers.seek(0)
    shutil.copyfileobj(buffers, output)


def _load_persistent_oob(source, opcodes: bytes, device: str | None):
  """Load upstream's aligned weight arena, retaining views into one allocation."""
  if not source.seekable():
    raise ValueError("persistent-buffer models must be installed as a single file")
  start = source.tell()
  source.seek(0, os.SEEK_END)
  arena_size = source.tell() - start
  source.seek(start)
  if arena_size <= 0:
    raise EOFError("missing persistent model buffers")
  arena = Buffer(device or Device.DEFAULT, arena_size, preallocate=True)
  chunk_size = 32 << 20
  for offset in range(0, arena_size, chunk_size):
    size = min(chunk_size, arena_size - offset)
    data = source.read(size)
    if len(data) != size:
      raise EOFError("truncated persistent model buffer arena")
    host = Buffer("PYTHON", size, opaque=memoryview(bytearray(data)))
    arena.view(size, offset).ensure_allocated().copy_from(host)

  def persistent_load(pid):
    # tinygrad d3f09c9b artifacts reference (nbytes, offset): Buffer has no dtype. The older (size, dtype, offset) form
    # comes from artifacts compiled for an earlier tinygrad pin, which must be recompiled for this one.
    if not isinstance(pid, tuple) or len(pid) != 2:
      raise ValueError("persistent model buffer reference is not (nbytes, offset): artifact was compiled for another tinygrad, recompile it")
    nbytes, offset = pid
    if not isinstance(nbytes, int) or not isinstance(offset, int) or nbytes <= 0 or offset < 0:
      raise ValueError("invalid persistent model buffer range")
    if offset + nbytes > arena_size:
      raise EOFError("persistent model buffer exceeds weight arena")
    return arena.view(nbytes, offset)

  unpickler = pickle.Unpickler(io.BytesIO(opcodes))
  unpickler.persistent_load = persistent_load
  return unpickler.load()


def load_oob(source, device: str | None = None):
  header = source.read(8)
  if len(header) != 8:
    raise EOFError("truncated out-of-band pickle header")
  opcode_size = struct.unpack("<q", header)[0]
  if not 2 <= opcode_size <= 1024 * 1024 * 1024:
    raise ValueError("invalid out-of-band opcode length")
  opcodes = source.read(opcode_size)
  if len(opcodes) != opcode_size:
    raise EOFError("truncated out-of-band opcodes")
  if any(op.name == "BINPERSID" for op, _, _ in pickletools.genops(opcodes)):
    return _load_persistent_oob(source, opcodes, device)

  def buffers():
    previous = None
    while header := source.read(8):
      if len(header) != 8:
        raise EOFError("truncated out-of-band buffer header")
      if previous is not None:
        previous.release()
      buffer = bytearray(struct.unpack("<q", header)[0])
      if source.readinto(buffer) != len(buffer):
        raise EOFError("truncated out-of-band buffer")
      previous = pickle.PickleBuffer(buffer)
      yield previous

  return pickle.load(io.BytesIO(opcodes), buffers=buffers())


def load_precompiled_artifact(path: Path, device: str | None = None):
  """A tinygrad examples/openpilot compile_onnx.py / compile_warp.py artifact (out-of-band weight arena), single file or
  chunked, onto `device` (default: tinygrad's default device)."""
  from openpilot.common.file_chunker import open_file_chunked
  with (path.open("rb") if path.is_file() else open_file_chunked(path)) as artifact_file:
    return load_oob(artifact_file, device=device)
