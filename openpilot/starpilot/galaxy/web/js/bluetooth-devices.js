export function hasBluetoothName(device) {
  if (typeof device?.name !== "string") return false
  const name = device.name.trim()
  const address = name.replace(/^[[(]|[\])]$/g, "").replace(/^dev_/i, "").replace(/[:.\s_-]/g, "")
  return name.length > 0 && !/^[0-9a-f]{12}$/i.test(address)
}

// Keep discovery rows in their first-seen position while updating live state.
export class BluetoothDeviceList {
  constructor() { this.reset() }
  reset() { this.order = [] }
  update(devices) {
    const current = new Map()
    for (const device of devices) {
      // An Android Auto receiver stays visible by address until BlueZ resolves its name
      if (!hasBluetoothName(device) && device.starport !== true) continue
      current.set(device.address, { ...device, name: hasBluetoothName(device) ? device.name.trim() : device.address })
      if (!this.order.includes(device.address)) this.order.push(device.address)
    }
    return this.order.filter((address) => current.has(address)).map((address) => current.get(address))
  }
}
