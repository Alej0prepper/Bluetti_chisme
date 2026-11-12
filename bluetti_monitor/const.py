"""Constants reverse-engineered from the Bluetti Android app (v3.0.9).

Source: net.poweroak.bluetticloud / net.poweroak.lib_ble decompiled with jadx.
See README.md and the project memory for the full protocol write-up.
"""

# ---------------------------------------------------------------------------
# BLE GATT (net.poweroak.lib_ble.BleConfig)
# ---------------------------------------------------------------------------
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"

# Advertised local-name prefixes.  Plaintext devices advertise as "BLUETTI…",
# encrypted (ESP32 / IoT) devices advertise as "BLUETTE…".
ADV_NAME_PLAINTEXT = "BLUETTI"
ADV_NAME_ENCRYPTED = "BLUETTE"

DEFAULT_SLAVE_ADDR = 0x01
FUNC_READ = 0x03           # read holding registers
FUNC_WRITE_SINGLE = 0x06   # write single register
FUNC_WRITE_MULTI = 0x10    # write multiple registers

# Max characteristic write payload before MTU negotiation.
WRITE_SPLIT_COUNT = 20

