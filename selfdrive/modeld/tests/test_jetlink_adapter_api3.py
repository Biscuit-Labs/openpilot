from types import SimpleNamespace

import pytest

from jetlink.openpilot.warp import LegacyWarp, Warp, Warps
from openpilot.starpilot import jetlink_adapter


def test_adapter_frame_callback_reads_fresh_controls():
  adapter = jetlink_adapter.Adapter()
  cc = SimpleNamespace(enabled=False, latActive=False, longActive=False)

  class SM(dict):
    fresh = True
    calls = []
    fail = False

    def update(self, timeout):
      self.calls.append(timeout)
      if self.fail:
        raise RuntimeError('service failed')

    def all_alive(self, services):
      return self.fresh

    def all_valid(self, services):
      return self.fresh

  adapter._sm = SM(carControl=cc)
  assert adapter.in_control() is False
  assert adapter._sm.calls == [0]
  for field in ('enabled', 'latActive', 'longActive'):
    setattr(cc, field, True)
    assert adapter.in_control() is True
    setattr(cc, field, False)
  adapter._sm.fresh = False
  assert adapter.in_control() is True
  adapter._sm.fail = True
  assert adapter.in_control() is True


def test_legacy_capture_dispatch_reaches_frame_runner():
  runner = object()
  sizes = []

  def make(size):
    sizes.append(size)
    return runner

  assert Warp(LegacyWarp(make), 1234) is runner
  assert sizes == [1234]


@pytest.mark.parametrize('names,shape', [
  (None, (2, 6, 128, 256)),
  (['frame'], (2, 6, 128, 256)),
  (['big_frame', 'big_tfm', 'frame', 'tfm'], (2, 6, 64, 128)),
])
def test_legacy_capture_rejects_invalid_names_or_geometry(names, shape):
  capture = None if names is None else SimpleNamespace(expected_names=names, ret=SimpleNamespace(shape=shape))
  with pytest.raises(RuntimeError):
    jetlink_adapter.Adapter().load_legacy_warp(SimpleNamespace(captured=capture), 512, 256)


def test_legacy_pickle_load_uses_adapter_validation(tmp_path, monkeypatch):
  adapter = jetlink_adapter.Adapter()
  path = tmp_path / 'warp.pkl'
  path.write_bytes(b'capture')
  monkeypatch.setattr(adapter, 'warp_path', lambda *args: path)
  jit = SimpleNamespace(captured=SimpleNamespace(
    expected_names=['big_frame', 'big_tfm', 'frame', 'tfm'], ret=SimpleNamespace(shape=(2, 6, 128, 256))))
  monkeypatch.setattr('jetlink.openpilot.warp.pickle.load', lambda f: jit)
  assert isinstance(Warps(adapter).load(1928, 1208, 512, 256), LegacyWarp)
  jit.captured.ret.shape = (1, 6, 128, 256)
  with pytest.raises(RuntimeError):
    Warps(adapter).load(1928, 1208, 512, 256)


def test_queue_model_reset_clears_actual_history():
  import numpy as np
  from tinygrad import Tensor
  from jetlink.openpilot.warp import prepare_reset

  queue = Tensor.ones(4, device='CPU').realize()
  model = SimpleNamespace(input_queues={'history': queue}, numpy_inputs={'desire': np.ones(8)}, prev_desire=np.ones(8))
  reset = prepare_reset(model)
  queue.assign(5).realize()
  reset()
  assert np.array_equal(queue.numpy(), np.zeros(4))
  assert np.array_equal(model.numpy_inputs['desire'], np.zeros(8))
  assert np.array_equal(model.prev_desire, np.zeros(8))


def test_legacy_frame_runner_with_real_cpu_capture():
  import numpy as np
  from tinygrad import Tensor, TinyJit

  @TinyJit
  def graph(tfm, big_tfm, frame, big_frame):
    return Tensor.stack(frame.reshape(6, 2, 2), big_frame.reshape(6, 2, 2)).contiguous().realize()

  transforms = [Tensor(np.eye(3, dtype=np.float32), device='NPY').realize() for _ in range(2)]
  inputs = [Tensor.ones(24, dtype='uint8', device='CPU').realize() for _ in range(2)]
  for _ in range(3):
    graph(tfm=transforms[0], big_tfm=transforms[1], frame=inputs[0], big_frame=inputs[1])
  capture = jetlink_adapter.Adapter().load_legacy_warp(graph, 4, 4)
  runner = Warp(capture, 24)
  frames = [np.arange(24, dtype=np.uint8), np.arange(24, dtype=np.uint8) + 30]
  runner.start(frames[0].ctypes.data, frames[1].ctypes.data, np.eye(3), np.eye(3))
  runner.wait()
  assert np.array_equal(np.frombuffer(runner.output, dtype=np.uint8), np.concatenate(frames))
