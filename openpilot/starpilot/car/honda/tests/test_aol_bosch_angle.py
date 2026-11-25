from opendbc.car.structs import car
from openpilot.starpilot.car.honda.aol import native_profile_supported

BOSCH = int(car.CarParams.SafetyModel.hondaBosch)
NIDEC = int(car.CarParams.SafetyModel.hondaNidec)


def test_bosch_angle_words_are_native_profiles():
  # 11-24 CR-V A220/A040 testers: stock ACC 0x3001, alpha long 0x3823 (angle bit 4096 + profile 1 in bits 15:13). Unmasked,
  # the native receipt refused them, pandad never published aolSafetyWire and Set raised commIssue.
  for word in (0x3001, 0x3823):
    assert native_profile_supported(BOSCH, word)
  for base in (1, 0x823, 2211):
    for profile in range(8):
      assert native_profile_supported(BOSCH, base | 0x1000 | (profile << 13))


def test_unlisted_bosch_words_stay_refused_with_angle_bits():
  for base in (2, 3, 0x40, 0x100):
    assert not native_profile_supported(BOSCH, base)
    assert not native_profile_supported(BOSCH, base | 0x1000 | (1 << 13))


def test_nidec_unchanged():
  assert native_profile_supported(NIDEC, 544 | 4096) and not native_profile_supported(NIDEC, 2 | 4096)
