"""Original EPS66 Prius four-byte filter; no smartDSU status is inferred."""
from opendbc.car import structs
from opendbc.car.toyota.advert_filter import AdvertFilterCANParser
from opendbc.car.toyota.values import CAR, ToyotaFlags

LONG_WORD = 0xC042
STOCK_WORD = 0xC242
WORDS = frozenset((LONG_WORD, STOCK_WORD))
RETROFIT_EPS = b'8965B47070\x00\x00\x00\x00\x00\x00'


def hardware_supported(candidate, fingerprint, car_fw):
  if (candidate != CAR.TOYOTA_PRIUS or fingerprint.get(0, {}).get(0x2FF) != 4 or
      any(0x2FF in messages and (bus != 2 or messages[0x2FF] != 4) for bus, messages in fingerprint.items() if bus != 0) or
      any(address in messages for messages in fingerprint.values() for address in (0x201, 0x2AA)) or
      any(fingerprint.get(0, {}).get(address, 8) != 8 for address in (0x1D3, 0x262)) or
      any(fingerprint.get(2, {}).get(address, 8) != 8 for address in (0x343, 0x4CB))):
    return False
  from opendbc.car.toyota.fingerprints import FW_VERSIONS
  known = FW_VERSIONS[candidate]
  required = {structs.CarParams.Ecu.eps, structs.CarParams.Ecu.fwdCamera}
  if any(ecu == structs.CarParams.Ecu.fwdRadar for ecu, _, _ in known):
    required.add(structs.CarParams.Ecu.fwdRadar)
  for ecu in required:
    observed = [fw for fw in car_fw if fw.ecu == ecu]
    if not observed or any(fw.logging or fw.bus != 0 or fw.brand != 'toyota' or
                           bytes(fw.fwVersion) not in known.get((ecu, fw.address, fw.subAddress or None), ()) or
                           ecu == structs.CarParams.Ecu.eps and bytes(fw.fwVersion) == RETROFIT_EPS for fw in observed):
      return False
  return True


def apply(cp):
  cp.flags |= int(ToyotaFlags.HYBRID | ToyotaFlags.LONG_FILTER | ToyotaFlags.RAISED_ACCEL_LIMIT)
  cp.safetyConfigs[0].safetyParam = LONG_WORD
  cp.openpilotLongitudinalControl = True
  cp.alphaLongitudinalAvailable = False


def configured(cp):
  if (cp is None or cp.brand != 'toyota' or cp.carFingerprint != CAR.TOYOTA_PRIUS or cp.notCar or cp.passive or
      cp.dashcamOnly or cp.secOcRequired or not cp.pcmCruise or len(cp.safetyConfigs) != 1 or
      cp.steerControlType != structs.CarParams.SteerControlType.torque):
    return False
  flags = int(ToyotaFlags.HYBRID | ToyotaFlags.LONG_FILTER | ToyotaFlags.RAISED_ACCEL_LIMIT)
  config = cp.safetyConfigs[0]
  return bool(cp.flags & ~int(ToyotaFlags.ZSS) == flags and
              config.safetyModel == structs.CarParams.SafetyModel.toyota and
              config.safetyParam == (LONG_WORD if cp.openpilotLongitudinalControl else STOCK_WORD))


def prepare_stock(cp):
  if not configured(cp):
    return False
  cp.openpilotLongitudinalControl = False
  cp.safetyConfigs[0].safetyParam = STOCK_WORD
  cp.autoResumeSng = False
  return True


class PriusAdvertCANParser(AdvertFilterCANParser):
  """The discriminator carries FD_BUTTON only; MAIN/EPS retain authority."""
  def __init__(self, *args):
    super().__init__(*args)
    self.hardware_ambiguous = False

  def update(self, strings, sendcan=False):
    batches = []
    for stamp, frames in strings:
      frames = list(frames)
      for address, data, bus in frames:
        if address in (0x201, 0x2AA) or address == 0x2FF and (bus not in (0, 2) or len(data) != 4):
          self.hardware_ambiguous = True
      batches.append((stamp, frames))
    return super().update(batches, sendcan)
