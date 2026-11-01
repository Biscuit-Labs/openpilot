from openpilot.starpilot.system.starport.bluetooth_bridge import STATUS_DEVICE_LIMIT, STATUS_NAME_LIMIT, status_devices, status_name


def device(i: int, name: str = '', **flags) -> dict:
  address = f'AA:BB:CC:DD:{i // 256:02X}:{i % 256:02X}'
  return {'path': f'/dev_{i}', 'address': address, 'name': name or address, 'paired': False, 'trusted': False,
          'connected': False, 'uuids': [], 'starport': False, **flags}


def test_receiver_survives_the_cap():
  devices = [device(i) for i in range(100)] + [device(200, starport=True), device(201, paired=True), device(202, connected=True)]
  result = status_devices(devices)
  assert len(result) == STATUS_DEVICE_LIMIT
  assert [item['address'] for item in result[:3]] == [devices[-3]['address'], devices[-1]['address'], devices[-2]['address']]
  assert set(result[0]) == {'address', 'name', 'paired', 'connected', 'starport'}


def test_long_names_are_trimmed_not_rejected():
  assert status_name('x' * STATUS_NAME_LIMIT) == 'x' * STATUS_NAME_LIMIT
  trimmed = status_devices([device(1, name='y' * 200)])[0]['name']
  assert len(trimmed) == STATUS_NAME_LIMIT and trimmed.endswith('…')
