from types import SimpleNamespace

import pytest

from jetlink.openpilot.warp import Warp, Warps, prepare_reset
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



def test_native_model_reset_clears_actual_history():
  import numpy as np
  from tinygrad import Tensor

  queue = Tensor.ones(4, device='CPU').realize()
  model = SimpleNamespace(input_queues={'history': queue}, state_pairs={'history': 'next_history'},
                          packed_input=np.ones(32, dtype=np.uint8), prev_desire=np.ones(8))
  reset = prepare_reset(model)
  queue.assign(5).realize()
  reset()
  assert np.array_equal(queue.numpy(), np.zeros(4))
  assert np.array_equal(model.packed_input, np.zeros(32))
  assert np.array_equal(model.prev_desire, np.zeros(8))


def test_native_frame_runner_with_real_cpu_capture(tmp_path, monkeypatch):
  import numpy as np
  from tinygrad import Tensor, TinyJit

  @TinyJit
  def graph(M_inv, input_frame):
    return (input_frame.reshape(2, 6, 2, 2) + M_inv.sum().cast('uint8')).contiguous().realize()

  specs = {'input_frame': ((2, 24), '|u1', 'CPU'), 'M_inv': ((2, 3, 3), '<f4', 'CPU')}
  inputs = {name: Tensor(np.zeros(shape, dtype=dtype), device=device).realize()
            for name, (shape, dtype, device) in specs.items()}
  for _ in range(3):
    graph(**inputs)
  artifact = {'run': graph, 'input_specs': specs}
  adapter = jetlink_adapter.Adapter()
  path = tmp_path / 'warp.pkl'
  path.write_bytes(b'capture')
  monkeypatch.setattr(adapter, 'warp_path', lambda *args: path)
  monkeypatch.setattr('jetlink.openpilot.warp.pickle.load', lambda f: artifact)
  loaded = Warps(adapter).load(1928, 1208, 4, 4)
  runner = Warp(loaded, 24)
  frames = [np.arange(24, dtype=np.uint8), np.arange(24, dtype=np.uint8) + 30]
  runner.start(frames[0].ctypes.data, frames[1].ctypes.data, np.eye(3), np.eye(3))
  runner.wait()
  assert np.array_equal(np.frombuffer(runner.output, dtype=np.uint8), np.concatenate(frames) + 6)
  with pytest.raises(RuntimeError):
    Warps(adapter).load(1928, 1208, 8, 8)
