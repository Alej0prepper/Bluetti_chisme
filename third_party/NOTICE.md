# bluetti-monitor

Source: https://github.com/j4m3z0r/bluetti-monitor
Commit: 72a46f1790ecc2be6c9c0d5b375e94e1506c44a0
License: MIT (see bluetti-monitor-LICENSE).

Retained: field decoding, Modbus framing and CRC helpers.
Modified: const.py removes all embedded encryption credentials; device.py removes
output writes; client.py is replaced by a read-only transport that optionally
calls the separately installed official BLUETTI SDK. crypto.py, CLI, MQTT and
protocol notes containing fixed keys are omitted. No private keys, SDK binaries
or device licences are distributed.

Official API reference (no binaries or source copied):
https://github.com/bluetti-official/bluetti-bluetooth-lib
examples/bluetti_mqtt/bluetti_mqtt/bluetooth/encrypt.py

No verified Elite 100 V2 hardware support is claimed. BLUETTI is a trademark
of its owner; this project is independent.
