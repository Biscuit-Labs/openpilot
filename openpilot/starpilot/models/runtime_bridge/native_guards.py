"""Compile-only port of the existing native guards to pinned tinygrad 02e.

PRIVATE AND UNQUALIFIED. Stored artifacts are prepared offline. Inference only
verifies their guarded form and lets the ordinary HCQ linker bind fresh addresses.
"""
from collections import Counter
from dataclasses import replace
import ctypes
import hashlib
import itertools
from pathlib import Path
import struct
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
  from _ctypes import _CData

from tinygrad import Device
from tinygrad.device import Buffer, Compiled, HCQ_RUNTIME_DEV
from tinygrad.dtype import AddrSpace, dtypes
from tinygrad.engine import realize
from tinygrad.renderer.cstyle import ClangRenderer
from tinygrad.runtime.autogen import libusb
from tinygrad.runtime.support import hcq2
from tinygrad.runtime.support.c import DLL
from tinygrad.uop.ops import Ops, PatternMatcher, ProgramInfo, UOp, UPat, graph_rewrite, pm_renumber_slots
from tinygrad.schedule.prepare import resolve_function, pm_inline_calls

if TYPE_CHECKING:
  class _LowerAndCompile(Protocol):
    def __call__(self, linear: UOp, verbose: bool = True) -> UOp: ...

  class _HCQCompiler(Protocol):
    lower_and_compile: _LowerAndCompile


FORMAT = "starpilot_native02e_guard_v1"
# This immutable proof field names the qualified executable implementation ABI,
# originally identified by the exact v9 source SHA. It is not this file's SHA.
# This successor changes typing/registration syntax only; the release policy
# separately pins its exact current source bytes. A behavior change requires a
# new proof ABI and qualification, never an alias for this baseline.
QUALIFIED_PROOF_IMPLEMENTATION_SHA256 = "895349c6d5745eb1c3d4cd5bd8e767b200e0ca31ecb92a5287735dc28ab8a0d5"
REVISION = "02e698160eed1751738212144a7ea2cfb160b3f1"
FENCE_SHA256 = "24ed559861c8636c1026cad9a244854bb2236b5ee8b91bf21c5efbf688fa4a69"
USB_SHA256 = "66a3dfe48ac17899862ab80160cf6dac2c9b9707234527ba0d808f3b68404114"
FFI_TAG = "starpilot_native02e_libusb_functions"
FFI_NAMES = ("libusb_control_transfer", "libusb_bulk_transfer", "libusb_submit_transfer", "libusb_handle_events_timeout")
WRAPPERS = dict(zip(FFI_NAMES, ("sp_control", "sp_bulk", "sp_submit", "sp_events"), strict=True))
GUARD_NAMES = frozenset((*WRAPPERS.values(), "sp_loop_touch", "sp_loop_check", "starpilot_bounded_wait"))
_PINNED_NATIVE = {"libbounded_wait.so": FENCE_SHA256, "libusb_guards.so": USB_SHA256}
_INSTALLATION = None


def _current_native_ffi_buffer(device):
  # Called at link time, not captured when tinygrad compiles a matcher callback.
  # The module-level indirection keeps a Protection/Buffer (and its addresses)
  # out of deconstruct_function's copied/pickled callback globals.
  protection = _INSTALLATION
  if protection is None or protection.role != "driving" or protection.ffi_buffer is None:
    raise ValueError("Native function table has no active driving installation")
  buffer = protection.ffi_buffer
  if device != HCQ_RUNTIME_DEV.device or buffer.device != device or buffer.nbytes != len(FFI_NAMES) * 8:
    raise ValueError("Native function table runtime storage changed")
  return buffer


def _resolve_native_ffi(b):
  if b.op is not Ops.ALLOC or b.tag != FFI_TAG or b.dtype is not dtypes.uint64 or b.shape != (len(FFI_NAMES),):
    raise ValueError("Native function table binding changed")
  return _current_native_ffi_buffer(b.device)


def _nodes(root):
  return tuple(root.toposort(enter_calls=True))


def _payloads(root):
  cpu = {u.src[-1] for u in _nodes(root)
         if u.op is Ops.PROGRAM and isinstance(u.arg, ProgramInfo) and u.arg.target.device == "CPU"}
  return Counter(hashlib.sha256(u.arg).hexdigest() for u in _nodes(root)
                 if u.op is Ops.BINARY and isinstance(u.arg, bytes) and u not in cpu)


def _constant(u, value):
  return u.vmin == u.vmax == value


def _name(call):
  return call.body.arg.name if call.op is Ops.CALL and call.body.op is Ops.CUSTOM_FUNCTION else None


def _calls(root):
  return tuple(u for u in _nodes(root) if _name(u) is not None)


def _predicate_leaves(condition, mandatory=True):
  """Boolean terms only: do not walk through load/callback side-effect inputs."""
  if condition.dtype is not dtypes.bool:
    raise ValueError("Native polling predicate is not boolean")
  if condition.op in (Ops.AND, Ops.OR):
    if len(condition.src) != 2:
      raise ValueError("Unknown native boolean connector")
    required = mandatory and condition.op is Ops.AND
    return tuple(term for child in condition.src for term in _predicate_leaves(child, required))
  if condition.op not in (Ops.CMPLT, Ops.CMPEQ, Ops.CMPNE):
    raise ValueError("Unknown native polling predicate")
  return ((condition, mandatory),)


def _pending_status(condition):
  # UOp.eq is represented as (value != 255) != True before simplification.
  if (condition.op is Ops.CMPNE and condition.src[1].dtype is dtypes.bool and
      _constant(condition.src[1], True)):
    inner = condition.src[0]
    return (inner.op is Ops.CMPNE and inner.src[0].op is Ops.LOAD and
            inner.src[0].dtype is dtypes.uint32 and _constant(inner.src[1], 0xff))
  return (condition.op is Ops.CMPEQ and condition.src[0].op is Ops.LOAD and
          condition.src[0].dtype is dtypes.uint32 and _constant(condition.src[1], 0xff))


def _polling_condition(condition):
  leaves = _predicate_leaves(condition)
  timers = [(term, limit, required) for term, required in leaves if term.op is Ops.CMPLT
            for limit in (1000, 30000) if _constant(term.src[1], limit)]
  if len(timers) == 1 and timers[0][2]:
    timer, limit, _ = timers[0]
    # The exact recognized deadline is delegated to the fixed native C guard.
    # All status/sequence/error predicates, including their dependencies, stay.
    return condition.substitute({timer: UOp.const(True, dtypes.bool)}, enter_calls=True), limit * 1_000_000
  if not timers and sum(required and _pending_status(term) for term, required in leaves) == 1:
    return condition, 10_000_000_000
  raise ValueError("Unqualified native USB polling condition")


def _checked_poll_exit(condition):
  """Exactly a uint64 guard result converted to boolean, before/after lowering."""
  if condition.dtype is not dtypes.bool:
    return False
  if condition.op is Ops.CAST and len(condition.src) == 1:
    call = condition.src[0]
  elif condition.op is Ops.CMPNE and len(condition.src) == 2:
    call, zero = condition.src
    if (zero.dtype is not dtypes.uint64 or
        not (zero.op is Ops.CONST and _constant(zero, 0) or
             zero.op is Ops.CAST and len(zero.src) == 1 and
             zero.src[0].op is Ops.CONST and _constant(zero.src[0], 0))):
      return False
  else:
    return False
  return call.dtype is dtypes.uint64 and len(call.src) == 3 and _name(call) == "sp_loop_check"


def _weak(root):
  return tuple(u for u in _nodes(root) if u.op is Ops.RANGE and u.dtype is dtypes.void)


def _host(call):
  if call.op is not Ops.CALL or not isinstance(call.arg.aux, hcq2.HCQInfo):
    raise ValueError("Expected actual 02e HCQ call")
  if call.arg.aux.device not in (("QCOM",), ("AMD",)):
    raise ValueError("Unsupported native guard device")
  program = call.body
  if (program.op is not Ops.PROGRAM or len(program.src) != 4 or
      not isinstance(program.arg, ProgramInfo) or program.arg.target.device != "CPU" or
      program.src[-1].op is not Ops.BINARY):
    raise ValueError("Expected complete compiled CPU host")
  sink = program.src[0]
  if sink.op is not Ops.SINK or sink.arg.name != "hcq_submit":
    raise ValueError("Unexpected CPU submission source")
  if any(u.op is Ops.CALL and u.body.op in (Ops.SINK, Ops.PROGRAM) for u in _nodes(sink)):
    raise ValueError("Nested submission was not completely lowered")
  return program, sink


def _proof(call):
  program, sink = _host(call)
  return {
    "device": list(call.arg.aux.device),
    "cpu_target": str(program.arg.target),
    "cpu_binary_sha256": hashlib.sha256(program.src[3].arg).hexdigest(),
    "cpu_source_sha256": hashlib.sha256(program.src[2].arg.encode()).hexdigest(),
    "opaque_payloads": dict(_payloads(sink)),
    "arguments": len(call.src) - 1,
    "native_calls": dict(Counter(_name(u) for u in _calls(sink))),
  }


def _load_library(path, expected, key, symbols):
  path = Path(path)
  if path.is_symlink() or not path.is_file():
    raise ValueError("Missing qualified native guard library")
  raw = path.read_bytes()
  if (hashlib.sha256(raw).hexdigest() != expected or len(raw) < 20 or
      raw[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<HH", raw, 16) != (3, 183)):
    raise ValueError("Native guard library identity or ABI changed")
  if key in DLL._loaded_:
    raise ValueError("Native guard library key already registered")
  lib = ctypes.CDLL(str(path.resolve()))
  for symbol in symbols:
    expected_address = ctypes.cast(getattr(lib, symbol), ctypes.c_void_p).value
    if not expected_address:
      raise ValueError("Missing guard export")
    for previous in DLL._loaded_.values():
      try:
        other = ctypes.cast(getattr(previous, symbol), ctypes.c_void_p).value
      except AttributeError:
        continue
      if other != expected_address:
        raise ValueError("Native guard symbol collision")
  DLL._loaded_[key] = lib
  return lib


def _fresh_scope(c):
  if not c.is_inline_call:
    return None
  # Do not enter nested function bodies or substitute their PARAM namespace.
  # Freshen this invocation's REG storage and ranges BEFORE argument binding,
  # so distinct locals cannot hash-cons together after PARAM substitution.
  body = graph_rewrite(c.body, pm_renumber_slots, ctx=UOp.unique_num, walk=True)
  return resolve_function(c.replace(src=(body, *c.src[1:])))


_INLINE = PatternMatcher([(UPat(Ops.CALL, name='c'), _fresh_scope)]) + pm_inline_calls


def inline_host_sink(sink):
  if sink.op is not Ops.SINK or sink.arg is None or sink.arg.name != 'hcq_submit':
    raise ValueError('Expected fresh outer native hcq_submit SINK')
  outer_params = {u for u in sink.toposort() if u.op is Ops.PARAM}
  flat = sink
  for _ in range(64):
    pending = [u for u in flat.toposort(enter_calls=True)
               if u.op is Ops.CALL and u.body.op in (Ops.SINK, Ops.LINEAR, Ops.PROGRAM)]
    if not pending:
      break
    if any(not u.is_inline_call for u in pending):
      raise ValueError('Unexpected already-outlined or non-inline host function')
    updated = graph_rewrite(flat, _INLINE, walk=True)
    if updated is flat:
      raise ValueError('Host function inlining made no progress')
    flat = updated
  else:
    raise ValueError('Host function nesting exceeds bounded inlining limit')
  if any(u.op is Ops.PARAM and u not in outer_params for u in flat.toposort()):
    raise ValueError('An outlined function-local PARAM escaped binding')
  flat = graph_rewrite(flat, pm_renumber_slots, ctx=itertools.count(), walk=True)
  ranges = [u for u in flat.toposort() if u.op is Ops.RANGE]
  regs = [u for u in flat.toposort() if u.op is Ops.BUFFER and u.addrspace is AddrSpace.REG]
  if len({u.arg for u in ranges}) != len(ranges) or len({u.arg.slot for u in regs}) != len(regs):
    raise ValueError('Flattened local identities are not unique')
  if sink.arg != flat.arg or sink.tag != flat.tag:
    raise ValueError('Outer host source identity changed')
  return flat




def _native_ffi_slot(sink, argument_count):
  params = tuple(u for u in _nodes(sink) if u.op is Ops.PARAM)
  slot = min((u.arg.slot for u in params if u.addrspace is AddrSpace.ALU and u.arg.slot >= 0), default=argument_count)
  if not 0 <= slot <= argument_count or any(u.addrspace is not AddrSpace.ALU and u.arg.slot >= slot for u in params):
    raise ValueError("Native host pointer/scalar parameter order changed")
  return slot


def _shift_native_params(sink, first_slot, argument_count):
  original = tuple(u for u in _nodes(sink) if u.op is Ops.PARAM)
  moving = tuple(u for u in original if u.arg.slot >= first_slot)
  if not moving:
    return sink
  # substitute recursively rewrites replacements. Disjoint temporary slots
  # make both phases simultaneous; no original or final slot is a temp key.
  temporary_start = max(argument_count, *(u.arg.slot for u in original)) + 2
  temporary = {u: u.replace(arg=replace(u.arg, slot=temporary_start + i)) for i, u in enumerate(moving)}
  final = {temporary[u]: u.replace(arg=replace(u.arg, slot=u.arg.slot + 1)) for u in moving}
  shifted = sink.substitute(temporary, enter_calls=True).substitute(final, enter_calls=True)
  expected = {u.replace(arg=replace(u.arg, slot=u.arg.slot + 1)) if u in temporary else u for u in original}
  actual = {u for u in _nodes(shifted) if u.op is Ops.PARAM}
  if actual != expected or len(actual) != len(original):
    raise ValueError("Native host parameter renaming lost an original binding")
  return shifted


def _verify_cpu_parameter_abi(program):
  # Clang emits PARAM declarations in the compiled LINEAR's order. CPUProgram
  # invokes every globals pointer first, then every ProgramInfo.vars scalar.
  linear = program.src[1]
  if linear.op is not Ops.LINEAR:
    raise ValueError("Native host has no compiled parameter declaration order")
  params = tuple(u for u in linear.src if u.op is Ops.PARAM)
  expected = (*program.arg.globals, *(u.arg.slot for u in program.arg.vars))
  if tuple(u.arg.slot for u in params) != expected:
    raise ValueError("Native CPU parameter ABI is misordered")
  boundary = len(program.arg.globals)
  if (any(u.addrspace is AddrSpace.ALU for u in params[:boundary]) or
      any(u.addrspace is not AddrSpace.ALU for u in params[boundary:])):
    raise ValueError("Native CPU parameter ABI mixes pointers and scalars")


def _fresh_host(call):
  if call.op is not Ops.CALL or not isinstance(call.arg.aux, hcq2.HCQInfo):
    raise ValueError('Expected fresh actual 02e HCQ call')
  if call.arg.aux.device not in (('QCOM',), ('AMD',)) or call.body.op is not Ops.SINK:
    raise ValueError('Native guards must precede CPU compilation/outlining')
  if call.body.arg is None or call.body.arg.name != 'hcq_submit':
    raise ValueError('Unknown fresh CPU host source')
  return call.body


class Protection:
  def __init__(self, role, fence_library, usb_library):
    if role not in ("driving", "monitoring"):
      raise ValueError("Unknown native model role")
    if HCQ_RUNTIME_DEV.device.split(":")[0] != "CPU":
      raise ValueError("Native guard requires actual CPU helper target")
    renderer = Device[HCQ_RUNTIME_DEV.device]._select_renderer(HCQ_RUNTIME_DEV)
    if not isinstance(renderer, ClangRenderer):
      raise ValueError("Native guard requires its qualified Clang host renderer")
    self.role, self.renderer, self.records = role, renderer, []
    self.fence_library = _load_library(fence_library, FENCE_SHA256, "starpilot_native02e_fence",
                                      ("starpilot_bounded_wait",))
    self.usb_library = None
    self.ffi_buffer = None
    self.ffi = None
    if role == "driving":
      self.usb_library = _load_library(usb_library, USB_SHA256, "starpilot_native02e_usb",
                                      (*WRAPPERS.values(), "sp_loop_touch", "sp_loop_check"))
      fields = {name: (typ, offset) for name, typ, offset, *_ in cast("list[tuple[str, type[_CData], int]]", libusb.struct_libusb_transfer._real_fields_)}
      if any(fields[name][1] != offset or ctypes.sizeof(fields[name][0]) != 4
             for name, offset in (("status", 16), ("length", 20), ("actual_length", 24))):
        raise ValueError("Unqualified native libusb transfer layout")
      if ctypes.sizeof(ctypes.c_void_p) != 8 or ctypes.sizeof(ctypes.c_ulong) != 8:
        raise ValueError("Unqualified native host ABI")
      addresses = [ctypes.cast(getattr(libusb.dll, name), ctypes.c_void_p).value for name in FFI_NAMES]
      if not all(addresses):
        raise ValueError("Missing native libusb functions")
      self.ffi_buffer = Buffer(HCQ_RUNTIME_DEV.device, len(addresses) * 8,
                               initial_value=b"".join(address.to_bytes(8, "little") for address in addresses))
      self.ffi = UOp.alloc((len(addresses),), dtypes.uint64, 0, device=HCQ_RUNTIME_DEV.device).rtag(FFI_TAG)
      previous = Compiled.pm_bufferize
      Compiled.pm_bufferize = previous + PatternMatcher([(UPat(Ops.ALLOC, tag=FFI_TAG, name="b"), _resolve_native_ffi)])
    self.source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    self.identity = {
      "format": FORMAT, "compiler_revision": REVISION,
      "implementation_sha256": QUALIFIED_PROOF_IMPLEMENTATION_SHA256,
      "fence_sha256": FENCE_SHA256, "usb_sha256": USB_SHA256,
      "host_target": str(self.renderer.target),
    }

  @staticmethod
  def _native(name, args, dtype):
    return UOp.custom_function(name, dtype=dtype).call(*args)

  def _compile(self, original, rewritten, args):
    before = _payloads(_fresh_host(original))
    if _payloads(rewritten) != before:
      raise ValueError("Opaque GPU payload changed before CPU compilation")
    updated = original.replace(src=(rewritten, *args))
    if updated.device != HCQ_RUNTIME_DEV.device:
      raise ValueError("Guard rewrite attempted non-CPU compilation")
    compiled = realize.lower_and_compile(UOp(Ops.LINEAR, src=(updated,))).src[0]
    program, sink = _host(compiled)
    if program.arg.target != self.renderer.target or _payloads(sink) != before:
      raise ValueError("CPU target or opaque GPU payload changed")
    _verify_cpu_parameter_abi(program)
    self._verify_call(compiled)
    self.records.append(_proof(compiled))
    return compiled

  def _qcom(self, call, sink):
    loops, replacements = _weak(sink), {}
    if len(loops) != 1:
      raise ValueError("Expected exactly one native QCOM fence")
    loop = loops[0]
    ends = [u for u in _nodes(sink) if u.op is Ops.BACKEDGE and u.src[1] is loop]
    if len(ends) != 1:
      raise ValueError("Unknown native QCOM loop boundary")
    done, _, condition = ends[0].src
    if done.op is not Ops.LOAD or done.dtype is not dtypes.uint64:
      raise ValueError("Unknown native QCOM timeline load")
    comparisons = [u for u in _nodes(condition) if u.op is Ops.CMPLT and u.src[0] is done]
    timers = [u for u in _nodes(condition) if u.op is Ops.CMPLT and _constant(u.src[1], 30000)]
    if len(comparisons) != 1 or len(timers) != 1:
      raise ValueError("Unknown native QCOM deadline condition")
    target = comparisons[0].src[1]
    if target.dtype is not dtypes.uint64 or loop in target.ranges:
      raise ValueError("Unknown native QCOM fence target")
    index = done.src[0]
    if index.op is not Ops.INDEX or len(index.src) != 2 or not _constant(index.src[1], 0):
      raise ValueError("Unknown native QCOM signal address")
    signal = index.src[0].without_after
    arguments = realize.get_call_arg_uops(call)
    if signal.op is not Ops.PARAM or not 0 <= signal.arg.slot < len(arguments):
      raise ValueError("Native QCOM timeline is not an outer parameter")
    outer = arguments[signal.arg.slot].without_after
    if outer.op is not Ops.ALLOC or outer.tag != "timeline" or outer.device != "QCOM":
      raise ValueError("Timeline is not the native QCOM allocation")
    pointer = index.substitute({loop: UOp(Ops.NOOP)}, enter_calls=True)
    replacements[ends[0]] = self._native("starpilot_bounded_wait", (pointer, target), dtypes.uint64)
    rewritten = sink.substitute(replacements, enter_calls=True)
    if _weak(rewritten):
      raise ValueError("An unguarded QCOM polling range remains")
    return self._compile(call, rewritten, call.src[1:])

  def _usb(self, call, sink):
    if self.role != "driving" or self.ffi is None or not Device["AMD"].is_usb:
      raise ValueError("Expected the actual native USB AMD device")
    return self._usb_rewrite(call, sink)

  def _usb_rewrite(self, call, sink):
    args = list(call.src[1:])
    argument_count = len(realize.get_call_arg_uops(call))
    if any(not a.is_bound_var for a in args[argument_count:]) or any(a.is_bound_var for a in args[:argument_count]):
      raise ValueError("Native bound-variable argument order changed")
    ffi_slot = _native_ffi_slot(sink, argument_count)
    sink = _shift_native_params(sink, ffi_slot, argument_count)
    pointer = UOp.param(ffi_slot, dtypes.uint64, (len(FFI_NAMES),), HCQ_RUNTIME_DEV.device, name="native_usb_functions")
    loops = _weak(sink)
    if not 1 <= len(loops) < 256 or len({r.arg for r in loops}) != len(loops):
      raise ValueError("Unknown native USB polling structure")
    specifications, ends = {}, {}
    for slot, loop in enumerate(loops):
      boundaries = [u for u in _nodes(sink) if u.op is Ops.BACKEDGE and u.src[1] is loop]
      if len(boundaries) != 1:
        raise ValueError("Unknown native USB loop boundary")
      end = boundaries[0]
      condition, timeout = _polling_condition(end.src[2])
      specifications[loop] = (slot, timeout)
      ends[end] = condition
    calls = _calls(sink)
    if any(_name(u) not in {*FFI_NAMES, "memcpy", "clock_gettime"} for u in calls):
      raise ValueError("Unqualified native USB callback")
    def scalar64(u):
      return UOp(Ops.CUSTOMI, src=(u,), arg=("((unsigned long)({0}))", dtypes.uint64))
    substitutions, touched = {}, set()
    for callback in calls:
      name = _name(callback)
      if name not in WRAPPERS:
        continue
      touches = []
      for loop, (slot, timeout) in specifications.items():
        token = next((a for a in callback.src[1:] if loop in a.ranges), None)
        if token is not None:
          touches.append(self._native("sp_loop_touch", (
            UOp.const(slot, dtypes.uint64), UOp.const(timeout, dtypes.uint64), scalar64(token)), dtypes.uint64))
          touched.add(loop)
      marker = sum(touches[1:], touches[0]) if touches else UOp.const(0, dtypes.uint64)
      function = pointer.index(FFI_NAMES.index(name)).load()
      substitutions[callback] = self._native(WRAPPERS[name], (
        function, *(scalar64(a) for a in callback.src[1:]), marker), dtypes.int32)
    if touched != set(specifications) or not substitutions:
      raise ValueError("A native USB polling loop has no entry guard")
    sink = sink.substitute(substitutions, enter_calls=True)
    # Substitution can rebuild range identities; immutable unique range args
    # are the previously checked stable lookup keys.
    by_arg = {loop.arg: (slot, timeout) for loop, (slot, timeout) in specifications.items()}
    expected_conditions = {end.src[1].arg: condition for end, condition in ends.items()}
    replacements = {}
    for end in _nodes(sink):
      if end.op is Ops.BACKEDGE and end.src[1].arg in by_arg:
        slot, _ = by_arg[end.src[1].arg]
        condition = expected_conditions[end.src[1].arg].substitute(substitutions, enter_calls=True)
        check = self._native("sp_loop_check", (condition.cast(dtypes.uint64), UOp.const(slot, dtypes.uint64)), dtypes.uint64)
        replacements[end] = end.replace(src=(end.src[0], end.src[1], check.cast(dtypes.bool)))
    if len(replacements) != len(loops):
      raise ValueError("Native USB loop protection is incomplete")
    rewritten = sink.substitute(replacements, enter_calls=True)
    args.insert(ffi_slot, self.ffi)
    if len(args) != len(call.src) or any(args[i + (i >= ffi_slot)] is not original for i, original in enumerate(call.src[1:])):
      raise ValueError("Native host call argument insertion lost an original binding")
    return self._compile(call, rewritten, args)

  def protect_call(self, call):
    original = _fresh_host(call)
    sink = inline_host_sink(original)
    if _payloads(sink) != _payloads(original):
      raise ValueError("Host scope binding changed opaque payloads")
    if any(_name(u) in GUARD_NAMES for u in _calls(sink)):
      raise ValueError("Refusing partial or repeated native protection")
    return self._qcom(call, sink) if call.arg.aux.device == ("QCOM",) else self._usb(call, sink)

  def _verify_call(self, call):
    program, sink = _host(call)
    if program.arg.target != self.renderer.target:
      raise ValueError("Native CPU target changed")
    _verify_cpu_parameter_abi(program)
    calls = _calls(sink)
    if call.arg.aux.device == ("QCOM",):
      if _weak(sink) or sum(_name(u) == "starpilot_bounded_wait" for u in calls) != 1:
        raise ValueError("QCOM native guard proof missing")
    else:
      if self.role != "driving" or not Device["AMD"].is_usb:
        raise ValueError("Native Chestnut identity missing")
      if any(_name(u) in FFI_NAMES for u in calls):
        raise ValueError("An unchecked native USB function remains")
      weak = _weak(sink)
      boundaries = [u for u in _nodes(sink) if u.op is Ops.BACKEDGE and u.src[1] in weak]
      if not weak or len(boundaries) != len(weak):
        raise ValueError("Native USB polling proof missing")
      for end in boundaries:
        cond = end.src[2]
        if not _checked_poll_exit(cond):
          raise ValueError("An unchecked native polling exit remains")
      if not any(_name(u) == "sp_loop_touch" for u in calls):
        raise ValueError("Native polling entry proof missing")
      markers = [u for u in _nodes(UOp.sink(*call.src[1:])) if u.op is Ops.ALLOC and u.tag == FFI_TAG]
      if len(markers) != 1 or markers[0].dtype is not dtypes.uint64 or markers[0].shape != (len(FFI_NAMES),):
        raise ValueError("Fresh native function table marker missing")
    return _proof(call)

  def _prepare(self, jit):
    # The only preparation path is fresh HCQ re-encoding from authenticated
    # pre-HCQ input. Stored outlined PROGRAMs are never reverse-inlined.
    self._verify(jit)
    return jit

  def _verify(self, jit):
    cap = getattr(jit, "captured", None)
    if cap is None or "linear" in cap.__dict__:
      raise ValueError("Native guard verification must precede captured execution/linking")
    for entry in cap._linear.src:
      call = entry.without_after
      if call.op is not Ops.CALL or not (call.body.op is Ops.STORE or isinstance(call.arg.aux, hcq2.HCQInfo)):
        raise ValueError("Unknown native captured schedule entry")
    calls = [u for u in _nodes(cap._linear) if u.op is Ops.CALL and isinstance(u.arg.aux, hcq2.HCQInfo)]
    if not calls:
      raise ValueError("Missing native guarded submission")
    return [self._verify_call(call) for call in calls]

  @staticmethod
  def _capture_items(artifact):
    return [(key, value) for key, value in artifact.items() if getattr(value, "captured", None) is not None]

  def prepare_artifact(self, artifact, chestnut=False):
    items = self._capture_items(artifact)
    expected = 3 if self.role == "driving" else 1
    if len(items) != expected or "_starpilot_native_guard" in artifact:
      raise ValueError("Unknown native artifact capture count or repeated preparation")
    if self.role == "driving" and (artifact.get("execution_device") != ("AMD" if chestnut else "QCOM") or
                                    artifact.get("warp_device") != "QCOM"):
      raise ValueError("Native driving backend contract changed")
    for _, jit in items:
      self._prepare(jit)
    artifact["_starpilot_native_guard"] = {
      "identity": self.identity,
      "captures": {repr(key): self._verify(jit) for key, jit in items},
    }
    return artifact

  def artifact(self, artifact, chestnut=False):
    items = self._capture_items(artifact)
    expected = 3 if self.role == "driving" else 1
    if len(items) != expected:
      raise ValueError("Unknown native artifact capture count")
    proof = artifact.get("_starpilot_native_guard")
    if not isinstance(proof, dict) or proof.get("identity") != self.identity:
      raise ValueError("Native artifact guard identity changed or missing")
    actual = {repr(key): self._verify(jit) for key, jit in items}
    if actual != proof.get("captures"):
      raise ValueError("Native compiled host proof changed")
    if self.role == "driving" and (artifact.get("execution_device") != ("AMD" if chestnut else "QCOM") or
                                    artifact.get("warp_device") != "QCOM"):
      raise ValueError("Native driving backend contract changed")
    return artifact

  def prepare_warp(self, jit):
    return self._prepare(jit)

  def warp(self, jit):
    # The loader must authenticate the complete known stock warp file first.
    self._verify(jit)
    return jit

  def install_fresh_guard(self):
    original = hcq2.lower_and_compile
    if original is not realize.lower_and_compile:
      raise ValueError("Native host compiler was already replaced")
    def guarded(linear: UOp, *args, **kwargs) -> UOp:
      replacements = {}
      for call in _nodes(linear):
        if call.op is not Ops.CALL or not isinstance(call.arg.aux, hcq2.HCQInfo):
          continue
        if call.body.op is Ops.SINK:
          replacements[call] = self.protect_call(call)
        elif call.body.op is Ops.PROGRAM:
          self._verify_call(call)
        else:
          raise ValueError("Unknown fresh native host body")
      prepared = linear.substitute(replacements, enter_calls=True)
      for call in _nodes(prepared):
        if call.op is Ops.CALL and realize._get_call_to_compile(call) is not None:
          raise ValueError("Residual unqualified compilation after native guards")
      # Every compiled host is guarded before returning to HCQ. This does not
      # execute the intermediate graph or ask a GPU compiler to rebuild kernels.
      return original(prepared, *args, **kwargs)

    cast("_HCQCompiler", hcq2).lower_and_compile = guarded


def install(role, fence_library, usb_library):
  global _INSTALLATION
  if _INSTALLATION is not None:
    if _INSTALLATION.role != role:
      raise ValueError("Native guard role cannot change")
    return _INSTALLATION
  candidate = Protection(role, fence_library, usb_library)
  candidate.install_fresh_guard()
  _INSTALLATION = candidate
  return candidate
