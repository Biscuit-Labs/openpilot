"""The 3X's second WLAN chain is powered (L23) and wlan is switched to 2x2; other devices are untouched."""
from unittest.mock import Mock, patch

import pytest

from openpilot.common.hardware.comma.hardware import HardwareComma, WIFI_CHAIN1_SUPPLY

HW = 'openpilot.common.hardware.comma.hardware'


def make(device_type):
  hardware = HardwareComma.__new__(HardwareComma)
  hardware.get_device_type = Mock(return_value=device_type)
  return hardware


class Supply:
  """Debugfs regulator files: enable reads back what was written, unless the write is refused."""
  def __init__(self, enabled, accepts=True):
    self.enabled, self.accepts, self.writes = enabled, accepts, []

  def read(self, path):
    assert path == f"{WIFI_CHAIN1_SUPPLY}/enable"
    return "1" if self.enabled else "0"

  def write(self, val, path):
    self.writes.append((path.rsplit('/', 1)[1], val))
    if path.endswith('/enable') and self.accepts:
      self.enabled = val == "1"


def run(device_type, supply, mask_output="wlan0     get_txchainmask:1  "):
  with patch(f'{HW}.sudo_read', side_effect=supply.read), patch(f'{HW}.sudo_write', side_effect=supply.write), \
       patch(f'{HW}.subprocess.check_output', return_value=mask_output) as check_output, \
       patch(f'{HW}.subprocess.run') as run_cmd:
    make(device_type).configure_wifi_chains()
  return check_output, run_cmd


@pytest.mark.parametrize('device_type', ['mici', 'tici', 'pc'])
def test_other_devices_are_untouched(device_type):
  supply = Supply(enabled=False)
  check_output, run_cmd = run(device_type, supply)
  assert supply.writes == []
  check_output.assert_not_called()
  run_cmd.assert_not_called()


def test_tizi_powers_chain1_in_normal_mode_then_sets_2x2():
  supply = Supply(enabled=False)
  _, run_cmd = run('tizi', supply)
  assert supply.writes == [('enable', '1'), ('mode', '2')]  # mode only sticks once the regulator is on
  assert [c.args[0] for c in run_cmd.call_args_list] == [
    ['sudo', 'iwpriv', 'wlan0', 'txchainmask', '3'],
    ['sudo', 'iwpriv', 'wlan0', 'rxchainmask', '3'],
  ]


def test_tizi_already_2x2_is_a_no_op():
  supply = Supply(enabled=True)
  _, run_cmd = run('tizi', supply, mask_output="wlan0     get_txchainmask:3  ")
  assert supply.writes == []
  run_cmd.assert_not_called()


def test_tizi_reapplies_masks_after_a_wlan_restart():
  supply = Supply(enabled=True)
  _, run_cmd = run('tizi', supply, mask_output="wlan0     get_txchainmask:1  ")
  assert supply.writes == []
  assert run_cmd.call_count == 2


def test_tizi_never_enables_2x2_without_chain1_power():
  supply = Supply(enabled=False, accepts=False)
  check_output, run_cmd = run('tizi', supply)
  assert supply.writes == [('enable', '1')]
  check_output.assert_not_called()
  run_cmd.assert_not_called()


def test_tizi_without_wlan0_does_nothing_more():
  supply = Supply(enabled=True)
  with patch(f'{HW}.sudo_read', side_effect=supply.read), patch(f'{HW}.sudo_write', side_effect=supply.write), \
       patch(f'{HW}.subprocess.check_output', side_effect=FileNotFoundError), patch(f'{HW}.subprocess.run') as run_cmd:
    make('tizi').configure_wifi_chains()
  run_cmd.assert_not_called()
