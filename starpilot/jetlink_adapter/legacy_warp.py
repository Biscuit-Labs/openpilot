"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

StarPilot compatibility for its four-input warp ABI (D-132).
Retained from zoompilot/jetlink 4b747aeb; the active fork build still emits
these captures. Upstream API 3 uses a separate two-input dictionary format.

The comma-side warp JIT: how it is built, where it lives, what loads it, how
the frame loop runs it (Warp), and the small model's reset for a fallback.

The warp stays on the comma (see model_state), and upstream's fused run_model
JIT (openpilot #38684) has no warp to borrow, so comma's make_warp graph is
JIT-compiled as a build target: the fork's build runs
`python -m jetlink.openpilot.warp` once per camera it builds for. A source
build makes the one for its own camera, a prebuilt release one for every
camera it installs on. Nothing compiles one at runtime: in modeld the ~9 s
compile would hold back the first frame on every ignition, and in a
provisioning run, which only runs offroad, it was lost to ignition. A device
without one runs the small model.

load() is what stands between a bad pickle and the car.

tinygrad is the fork's, and only modeld and the build have it: every import of
it here is inside the function that needs it.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

# what TinyJit records for the keyword call in call_warp: sorted(kwargs)
WARP_INPUT_NAMES = ['big_frame', 'big_tfm', 'frame', 'tfm']
# KGSL allocation flags (msm_kgsl.h) for memory the GPU's accesses snoop the
# CPU's caches on, mapped write-back: KGSL_MEMFLAGS_IOCOHERENT, which
# tinygrad's kgsl bindings lack, and KGSL_CACHEMODE_WRITEBACK (3 << 26). See
# Warp
COHERENT_WRITEBACK = (1 << 31) | (3 << 26)
# camera buffers a Warp holds tensors for past which the log asks why.
# camerad hands out a fixed pool of 18 a stream and maps new ones only when
# it restarts, which modeld survives; past two generations of both streams
# something is rotating addresses under the cache, which otherwise grows
# without a bound
FRAMES_WARN = 2 * 2 * 18 + 1


def call_warp(warp, tfm, big_tfm, frame, big_frame):
  """Call a warp JIT. Every caller goes through here, capture included.

  TinyJit names inputs from enumerate(args) plus sorted(kwargs) and refuses a
  call whose names differ from the capture. A positional compile and a keyword
  call raised JitError on the first frame of a drive.
  """
  return warp(tfm=tfm, big_tfm=big_tfm, frame=frame, big_frame=big_frame)


class Warp:
  """The built warp as modeld's frame loop runs it: start() with two camera
  buffers and their transforms, wait(), and `output` holds the warped frame,
  where the link sends it from.

  Three things the JIT alone does not do, each measured on the comma
  (2026-10-06):
  - Its output lives in GPU memory the CPU reads through its cache. tinygrad
    maps a QCOM buffer write-combined, which the CPU reads uncached: copying
    the 393 KB out took 2.9 ms, the kernel's copy straight from that mapping
    7.3 ms. The Adreno 630 is IO-coherent, so KGSL memory flagged IOCOHERENT
    and write-back is right to read once the GPU is done: 0.22 ms for the
    kernel's copy, the GPU's own time unchanged. It moves before the first
    call, which binds the graph to its buffers' addresses.
  - A frame replays the capture with its inputs' buffers. TinyJit prepares
    and checks every call's inputs, a graph rewrite per input: 0.97 ms of a
    1.93 ms call. Every frame's inputs are alike (camera buffers as from_blob
    tensors, two transforms), and the buffers are all TinyJit's preparing
    hands the capture, so they are checked once, by the warm-up's calls
    through TinyJit.
  - On the GPU only the capture's graph of warp kernels runs. Replayed whole,
    the capture is three steps through tinygrad's dispatch, two of them
    copying a transform from an NPY tensor into its QCOM buffer through a
    synced memory view: 0.61 ms of a 1.13 ms launch on the frame loop, the
    graph's submit the rest (2026-10-07). start() writes the transforms into
    those buffers itself, as the copies did; the GPU is idle there, since
    every start() is waited for before the next.
  - A camera buffer becomes a tensor once, by address.

  The warm-up is the first call's 1.9 s and the second's compile, paid here
  rather than on modeld's frame loop, where it was ~26 dropped frames and
  16 s of modeldLagging after every join.
  """

  def __init__(self, jit, frame_size: int, log):
    import numpy as np
    from tinygrad.device import Device
    from tinygrad.tensor import Tensor
    self._frame_size = frame_size
    self._log = log
    self._tensor = Tensor
    out = jit.captured.ret.uop.base.buffer
    self._device = out.device
    if self._device.startswith('QCOM'):
      _make_coherent(out)
    # written in place by start(): the NPY tensors are views of them
    self._tfm = np.zeros((3, 3), dtype=np.float32)
    self._big_tfm = np.zeros((3, 3), dtype=np.float32)
    tfm, big_tfm = (Tensor(a, device='NPY').realize() for a in (self._tfm, self._big_tfm))
    self._tfm_buf, self._big_tfm_buf = tfm.uop.base, big_tfm.uop.base
    self._frames: dict[int, object] = {}   # camera buffer address -> its tensor
    blank = [np.zeros(frame_size, dtype=np.uint8) for _ in range(2)]
    blobs = [Tensor.from_blob(b.ctypes.data, (frame_size,), dtype='uint8', device=self._device) for b in blank]
    for _ in range(2):
      call_warp(jit, tfm, big_tfm, blobs[0], blobs[1])
    self.wait = Device[self._device].synchronize
    self.wait()
    self.output = out.as_memoryview(force_zero_copy=True, no_sync=True)
    self._replay = jit.captured
    if self._device.startswith('QCOM'):
      inputs = (blobs[1].uop.base, self._big_tfm_buf, blobs[0].uop.base, self._tfm_buf)
      self._replay, self._tfm, self._big_tfm = _graph_alone(jit.captured, inputs)

  def start(self, frame: int, big_frame: int, tfm, big_tfm) -> None:
    """Warp the camera buffers at these addresses under their transforms.
    `output` is the frame once wait() returns, until the next start()."""
    self._tfm[:, :] = tfm
    self._big_tfm[:, :] = big_tfm
    # the capture's input order, sorted names (WARP_INPUT_NAMES)
    self._replay((self._buffer(big_frame), self._big_tfm_buf, self._buffer(frame), self._tfm_buf), {})

  def _buffer(self, address: int):
    tensor = self._frames.get(address)
    if tensor is None:
      tensor = self._frames[address] = self._tensor.from_blob(address, (self._frame_size,), dtype='uint8',
                                                              device=self._device)
      if len(self._frames) == FRAMES_WARN:
        self._log.warning("jetlink: %d camera buffers cached; is the camera stack rotating them?", len(self._frames))
    return tensor.uop.base


def _graph_alone(captured, inputs):
  """The capture's graph of warp kernels, and the QCOM buffers its two copy
  steps write the transforms into, as (3, 3) float32 views: tfm's, then
  big_tfm's. Raises unless the capture is those three steps."""
  import numpy as np
  from tinygrad.engine.realize import get_graph_runtime, resolve_params
  from tinygrad.uop.ops import Ops
  steps = captured._linear.src
  copies = [s for s in steps if s.src[0].op is Ops.COPY]
  graphs = [s.src[0] for s in steps if s.src[0].op is Ops.CUSTOM_FUNCTION and s.src[0].arg == 'graph']
  if len(steps) != 3 or len(copies) != 2 or len(graphs) != 1:
    raise RuntimeError(f"the warp's capture is not two transform copies and a graph: {[s.src[0].op for s in steps]}")
  views = {}
  for step in copies:
    dest, src = resolve_params(step, inputs)
    name = WARP_INPUT_NAMES[next(i for i, u in enumerate(inputs) if u is src)]
    views[name] = np.frombuffer(dest.buffer.as_memoryview(force_zero_copy=True), dtype=np.float32).reshape(3, 3)
  return get_graph_runtime(graphs[0], inputs), views['tfm'], views['big_tfm']


def _make_coherent(out) -> None:
  """Move a QCOM buffer to KGSL memory flagged IOCOHERENT and write-back.
  Raises if the kernel keeps either flag back (the allocation's record holds
  its answer): write-back memory that is not coherent reads stale frames."""
  from tinygrad.device import Device
  dev = Device[out.device]
  mem = dev._gpu_alloc(out.nbytes, flags=COHERENT_WRITEBACK)
  if mem.meta[0].flags & COHERENT_WRITEBACK != COHERENT_WRITEBACK:
    dev._gpu_free(mem)
    raise RuntimeError(f"the GPU driver kept back IO-coherent memory (flags {mem.meta[0].flags:#x})")
  out.deallocate()
  out.allocate(opaque=mem)


# -- the build ------------------------------------------------------------------

def compile_warp(graph, frame_size: int, out: Path) -> Path:
  """JIT the warp graph and pickle it to `out`. Holds the GPU while it runs.

  Three runs before pickling: TinyJit captures on the second call, and a
  pickle taken earlier is an empty jit that silently does nothing.
  """
  import numpy as np
  from tinygrad.device import Device
  from tinygrad.engine.jit import TinyJit
  from tinygrad.tensor import Tensor

  warp_jit = TinyJit(graph, prune=True)

  # one set of input tensors: TinyJit captures against the buffers it is
  # first handed. Random so nothing constant-folds
  rng = np.random.default_rng(42)
  tfm_npy, big_tfm_npy = np.eye(3, dtype=np.float32), np.eye(3, dtype=np.float32)
  tfm = Tensor(tfm_npy, device='NPY')
  big_tfm = Tensor(big_tfm_npy, device='NPY')
  frame = Tensor.randint(frame_size, low=0, high=256, dtype='uint8', device=Device.DEFAULT).realize()
  big_frame = Tensor.randint(frame_size, low=0, high=256, dtype='uint8', device=Device.DEFAULT).realize()
  for _ in range(3):
    tfm_npy[:] = rng.standard_normal((3, 3)).astype(np.float32)
    big_tfm_npy[:] = rng.standard_normal((3, 3)).astype(np.float32)
    call_warp(warp_jit, tfm, big_tfm, frame, big_frame).realize()
  Device.default.synchronize()

  out = Path(out)
  out.parent.mkdir(parents=True, exist_ok=True)
  # through a temporary: a compile killed mid-write leaves nothing under the
  # name load() opens
  tmp = out.with_suffix('.pkl.tmp')
  with open(tmp, 'wb') as f:
    pickle.dump(warp_jit, f)
  tmp.replace(out)
  return out


def size(text: str) -> tuple[int, int]:
  """'WxH' as (w, h)."""
  w, sep, h = text.lower().partition('x')
  if not sep:
    raise argparse.ArgumentTypeError(f"expected WxH, not {text!r}")
  try:
    return int(w), int(h)
  except ValueError:
    raise argparse.ArgumentTypeError(f"expected WxH, not {text!r}") from None


def main(argv: list[str] | None = None) -> None:
  """Build the warp for one camera, as the fork's build runs it."""
  from jetlink.openpilot.interface import load_adapter
  p = argparse.ArgumentParser(prog='python -m jetlink.openpilot.warp', description=main.__doc__)
  p.add_argument('--adapter', required=True, help="the fork's adapter module")
  p.add_argument('--camera', type=size, required=True, help='camera resolution, WxH')
  p.add_argument('--model', type=size, required=True, help='model input, WxH')
  p.add_argument('--output', type=Path, required=True)
  args = p.parse_args(argv)

  (cam_w, cam_h), (model_w, model_h) = args.camera, args.model
  op = load_adapter(args.adapter)
  print(f"Compiling jetlink warp for {cam_w}x{cam_h} -> {model_w}x{model_h}...")
  # before anything of tinygrad's is imported here: comma's graph module
  # patches tinygrad's firmware fetch as it loads
  graph, frame_size = op.make_warp(cam_w, cam_h, model_w, model_h)
  out = compile_warp(graph, frame_size, args.output)
  print(f"  Saved to {out}")


if __name__ == "__main__":
  sys.exit(main())
