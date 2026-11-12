import asyncio
import contextlib
import math
import time
from collections import deque
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner
from bluetti_monitor.client import BluettiClient
from bluetti_monitor.device import BluettiDevice
from bluetti_monitor.const import SERVICE_UUID


def now():
    return datetime.now(timezone.utc).isoformat()


def advertisement(device, adv):
    name = adv.local_name or device.name or "Sin nombre"
    raw = b"".join(adv.manufacturer_data.values()).upper()
    identity = name.upper().encode() + raw
    candidate = any(x in identity for x in (b"BLUETT", b"EL100", b"ELITE")) or SERVICE_UUID in adv.service_uuids
    encrypted = True if b"BLUETTE" in identity else False if b"BLUETTI" in identity else None
    return {"address": device.address, "name": name, "rssi": adv.rssi,
            "candidate": candidate, "encrypted": encrypted,
            "manufacturer_data": {str(k): v.hex() for k, v in adv.manufacturer_data.items()},
            "service_uuids": adv.service_uuids}


class Explorer:
    def __init__(self, demo=False):
        self.demo = demo
        self.lock = asyncio.Lock()
        self.client = None
        self.device = None
        self.selected = None
        self.devices = {}
        self.services = []
        self.logs = deque(maxlen=150)
        self.history = deque(maxlen=720)
        self.values = {}
        self.updated_at = None
        self.error = None
        self.telemetry = False
        self.task = None
        self.demo_connected = False

    def log(self, message):
        self.logs.append({"at": now(), "message": message})

    @property
    def connected(self):
        return self.demo_connected if self.demo else bool(self.client and self.client.is_connected)

    def snapshot(self):
        connected = self.connected
        return {"demo": self.demo, "connected": connected, "telemetry": self.telemetry and connected,
                "selected": self.selected, "services": self.services, "values": self.values,
                "updated_at": self.updated_at, "error": self.error,
                "stale": bool(self.updated_at and (not connected or not self.telemetry)),
                "history": list(self.history), "logs": list(self.logs)}

    async def scan(self):
        async with self.lock:
            if self.connected:
                raise ValueError("Desconecta el equipo antes de buscar otra vez.")
            self.log("Buscando dispositivos BLE durante 8 segundos…")
            if self.demo:
                self.devices = {"DEMO": {"address": "DEMO", "name": "Elite 100 V2 · DEMO", "candidate": True,
                                        "rssi": -48, "encrypted": True, "manufacturer_data": {}, "service_uuids": [SERVICE_UUID]}}
            else:
                found = await BleakScanner.discover(timeout=8, return_adv=True)
                self.devices = {dev.address: advertisement(dev, adv) for dev, adv in found.values()}
            self.log(f"Búsqueda terminada: {len(self.devices)} dispositivos.")
            return sorted(self.devices.values(), key=lambda d: (not d["candidate"], -d["rssi"]))

    async def _close(self):
        self.telemetry = False
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        if self.client:
            await self.client.disconnect()
        self.client = self.device = None
        self.demo_connected = False

    async def disconnect(self):
        async with self.lock:
            await self._close()
            self.log("Bluetooth desconectado.")
        return self.snapshot()

    async def connect(self, address):
        async with self.lock:
            if address not in self.devices:
                raise ValueError("Busca y selecciona un dispositivo antes de conectar.")
            await self._close()
            self.selected = self.devices[address]
            self.services, self.values = [], {}
            self.history.clear()
            self.updated_at = self.error = None
            try:
                if self.demo:
                    self.demo_connected = True
                    self.services = [{"uuid": SERVICE_UUID, "description": "Servicio simulado",
                                      "characteristics": [{"uuid": "0000ff01-0000-1000-8000-00805f9b34fb", "properties": ["notify"], "handle": 1}]}]
                else:
                    self.client = BleakClient(address, timeout=20)
                    await asyncio.wait_for(self.client.connect(), 30)
                    self.services = [{"uuid": s.uuid, "description": s.description,
                                      "characteristics": [{"uuid": c.uuid, "handle": c.handle,
                                                           "properties": c.properties} for c in s.characteristics]}
                                     for s in self.client.services]
                self.log("Conexión BLE establecida. Servicios GATT disponibles.")
            except Exception:
                await self._close()
                raise
        return self.snapshot()

    async def start_telemetry(self, encryption="auto"):
        async with self.lock:
            if not self.selected or not self.connected:
                raise ValueError("Conecta un dispositivo primero.")
            selected = self.selected
            await self._close()
            self.error = None
            try:
                if self.demo:
                    self.demo_connected = True
                else:
                    encrypted = selected["encrypted"] if encryption == "auto" else encryption == "encrypted"
                    # Unknown advertisements: try encrypted for the Elite V2 family.
                    if encrypted is None:
                        encrypted = True
                    self.client = BluettiClient(selected["address"], encrypted=encrypted, timeout=12)
                    self.log(f"Abriendo protocolo {'cifrado' if encrypted else 'sin cifrar'}…")
                    await asyncio.wait_for(self.client.connect(), 45)
                    self.device = BluettiDevice(self.client, layout="v2")
                await self._sample()
                self.telemetry = True
                self.task = asyncio.create_task(self._poll())
                self.log("Telemetría activa. Lectura cada 5 segundos.")
            except Exception as exc:
                self.error = f"No se pudo leer el protocolo V2: {str(exc) or type(exc).__name__}. Puedes reconectar para explorar GATT o probar otro modo de cifrado."
                self.log(self.error)
                await self._close()
        return self.snapshot()

    async def _sample(self):
        if self.demo:
            t = time.monotonic()
            values = {"device_model": "EL100V2 (DEMO)", "battery_soc": 76,
                      "pack_voltage": 51.2, "pack_current": -3.2,
                      "ac_output_power": round(160 + math.sin(t / 6) * 35),
                      "dc_output_power": 18, "pv_input_power": 0, "grid_power": 0,
                      "ac_output": "ON", "dc_output": "ON"}
        else:
            values = await asyncio.wait_for(self.device.poll(), 35)
            soc = values.get("battery_soc")
            if not isinstance(soc, (int, float)) or not 0 <= soc <= 100:
                raise ValueError("SOC inválido; el mapa V2 puede no coincidir con este firmware")
        self.values = values
        self.updated_at = now()
        self.history.append({"at": self.updated_at, **values})

    async def _poll(self):
        try:
            while True:
                await asyncio.sleep(5)
                await self._sample()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.telemetry = False
            self.error = f"Lecturas detenidas: {str(exc) or type(exc).__name__}. Reconecta para reintentar."
            self.log(self.error)
            if self.client:
                with contextlib.suppress(Exception):
                    await self.client.disconnect()

    async def read_characteristic(self, handle):
        async with self.lock:
            if not self.connected or self.telemetry:
                raise ValueError("Usa el modo GATT conectado, con la telemetría detenida.")
            characteristic = next((c for s in self.services for c in s["characteristics"] if c["handle"] == handle), None)
            if not characteristic or "read" not in characteristic["properties"]:
                raise ValueError("Esta característica no permite lectura GATT.")
            data = b"DEMO" if self.demo else await asyncio.wait_for(self.client.read_gatt_char(handle), 12)
            self.log(f"Lectura GATT {handle}: {data.hex()}")
            return {"hex": data.hex(), "text": data.decode("utf-8", errors="replace")}
