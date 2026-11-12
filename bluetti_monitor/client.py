"""Read-only BLE transport. Optional encryption delegates to BLUETTI's local SDK.

No private keys or embedded protocol secrets are distributed with this client.
Framing and field decoders are adapted from bluetti-monitor (MIT).
"""
from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

from bleak import BleakClient, BleakScanner
from . import const
from .protocol import ModbusError, build_read_command, parse_read_response


class BluettiClientError(Exception):
    pass


class BluettiClient:
    def __init__(self, address, encrypted=False, timeout=12):
        self.address, self.encrypted, self.timeout = address, encrypted, timeout
        self._client = None
        self._write_char = None
        self._sdk = None
        self._ready = asyncio.Event()
        self._response = None
        self._rx = bytearray()
        self._lock = asyncio.Lock()
        self._handshake_tasks = set()
        self._handshake_error = None

    async def connect(self):
        if self.encrypted:
            try:
                module = importlib.import_module("bluetti_crypt")
            except (ImportError, OSError) as exc:
                raise BluettiClientError("El modo cifrado necesita el módulo oficial bluetti_crypt instalado localmente; consulta README > Cifrado oficial") from exc
            if not Path("bluetti_device_licence.csv").is_file():
                raise BluettiClientError("Falta bluetti_device_licence.csv para tu dispositivo en la carpeta de ejecución")
            self._sdk = module.BluettiCrypt()
        target = await BleakScanner.find_device_by_address(self.address, timeout=self.timeout)
        self._client = BleakClient(target or self.address, timeout=self.timeout)
        await self._client.connect()
        service = self._client.services.get_service(const.SERVICE_UUID)
        if service is None:
            raise BluettiClientError("No se encontró el servicio BLUETTI FF00")
        self._write_char = service.get_characteristic(const.WRITE_UUID)
        if self._write_char is None:
            raise BluettiClientError("No se encontró la característica FF02")
        await self._client.start_notify(const.NOTIFY_UUID, self._notify)
        if self.encrypted:
            await asyncio.wait_for(self._ready.wait(), self.timeout)
            if self._handshake_error:
                raise BluettiClientError(self._handshake_error)
            if self._handshake_tasks:
                await asyncio.gather(*tuple(self._handshake_tasks))

    @property
    def is_connected(self):
        return bool(self._client and self._client.is_connected)

    async def disconnect(self):
        for task in tuple(self._handshake_tasks):
            task.cancel()
        if self._handshake_tasks:
            await asyncio.gather(*self._handshake_tasks, return_exceptions=True)
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
        self._sdk = None

    async def _raw_write(self, payload):
        size = max(20, getattr(self._write_char, "max_write_without_response_size", 20))
        for offset in range(0, len(payload), size):
            await self._client.write_gatt_char(self._write_char, payload[offset:offset+size], response=False)
            await asyncio.sleep(.02)

    async def _reply_handshake(self, payload):
        try:
            await self._raw_write(payload)
        except Exception as exc:
            self._handshake_error = f"Fallo al responder a la negociación: {type(exc).__name__}"
            self._ready.set()

    def _notify(self, characteristic, data):
        try:
            if self._sdk and not self._ready.is_set():
                # API documented by bluetti-official's Python examples.
                message, status = self._sdk.ble_crypt_link_handler(bytes(data))
                if message:
                    task = asyncio.create_task(self._reply_handshake(bytes(message)))
                    self._handshake_tasks.add(task)
                    task.add_done_callback(self._handshake_tasks.discard)
                if status == 4:
                    self._ready.set()
                elif status < 0:
                    self._handshake_error = f"El SDK oficial rechazó la autenticación (estado {status})"
                    self._ready.set()
                return
            payload = self._sdk.decrypt_data(bytes(data)) if self._sdk else data
            if not payload or self._response is None or self._response.done():
                return
            self._rx.extend(payload)
            if len(self._rx) < 3:
                return
            length = 5 if self._rx[1] & 0x80 else self._rx[2] + 5
            if len(self._rx) >= length:
                frame = bytes(self._rx[:length])
                self._response.set_result(frame)
                self._rx.clear()
        except Exception as exc:
            if self._response is not None and not self._response.done():
                self._response.set_exception(BluettiClientError(f"Fallo decodificando respuesta: {type(exc).__name__}"))
            elif not self._ready.is_set():
                self._handshake_error = f"Fallo del SDK durante la negociación: {type(exc).__name__}"
                self._ready.set()

    async def read_registers(self, addr, count, retries=2):
        async with self._lock:
            for attempt in range(retries+1):
                self._rx.clear()
                self._response = asyncio.get_running_loop().create_future()
                try:
                    command = build_read_command(addr, count)
                    if self._sdk:
                        command = self._sdk.encrypt_data(command)
                        if not command:
                            raise BluettiClientError("El SDK no pudo cifrar la solicitud")
                    await self._raw_write(command)
                    frame = await asyncio.wait_for(self._response, self.timeout)
                    response = parse_read_response(frame)
                    if response.slave != const.DEFAULT_SLAVE_ADDR or response.function != const.FUNC_READ or len(response.registers) != count:
                        raise ModbusError("La respuesta no coincide con la lectura solicitada")
                    return response
                except (asyncio.TimeoutError, ModbusError) as exc:
                    if attempt >= retries:
                        raise BluettiClientError(f"Sin respuesta válida para registros {addr}/{count}") from exc
                finally:
                    self._response = None
