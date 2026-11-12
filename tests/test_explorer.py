import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from explorer.app import create_app
from explorer.manager import Explorer, advertisement


def test_advertisement_encryption_in_manufacturer_data():
    dev = SimpleNamespace(address="AA:BB", name="EL100V2")
    adv = SimpleNamespace(local_name=None, manufacturer_data={123: b"BLUETTE123"}, rssi=-40, service_uuids=[])
    result = advertisement(dev, adv)
    assert result["candidate"] is True
    assert result["encrypted"] is True
    assert result["manufacturer_data"]["123"] == b"BLUETTE123".hex()


def test_unknown_advertisement_does_not_claim_plaintext():
    dev = SimpleNamespace(address="AA:BB", name="EL100V2")
    adv = SimpleNamespace(local_name=None, manufacturer_data={}, rssi=-40, service_uuids=[])
    assert advertisement(dev, adv)["encrypted"] is None


def test_demo_full_flow_and_export():
    app = create_app(demo=True)
    with TestClient(app) as c:
        assert c.get("/").status_code == 200
        assert c.get("/static/app.js").status_code == 200
        assert not c.get("/api/state").json()["connected"]
        devices = c.post("/api/scan").json()
        assert devices[0]["address"] == "DEMO"
        s = c.post("/api/connect", json={"address": "DEMO"}).json()
        assert s["connected"] and not s["telemetry"] and s["services"]
        assert c.post("/api/scan").status_code == 400
        s = c.post("/api/telemetry", json={"encryption": "auto"}).json()
        assert s["telemetry"] and s["demo"]
        assert s["values"]["battery_soc"] == 76
        assert len(s["history"]) == 1
        assert c.get("/api/export").headers["content-disposition"].endswith('"bluetti-diagnostico.json"')
        s = c.post("/api/disconnect").json()
        assert not s["connected"] and not s["telemetry"] and s["stale"]
        assert app.state.manager.task is None


def test_invalid_actions_and_cross_origin_blocked():
    with TestClient(create_app(demo=True)) as c:
        assert c.post("/api/connect", json={"address": "unknown"}).status_code == 400
        assert c.post("/api/telemetry", json={"encryption": "magic"}).status_code == 400
        assert c.post("/api/gatt/1").status_code == 400
        assert c.post("/api/scan", headers={"Origin": "https://evil.example"}).status_code == 403
        assert c.get("/", headers={"Host": "evil.example"}).status_code == 400


@pytest.mark.asyncio
async def test_failed_protocol_handshake_cleans_up(monkeypatch):
    instances = []

    class BrokenClient:
        def __init__(self, *args, **kwargs):
            self.is_connected = False
            self.disconnected = False
            instances.append(self)
        async def connect(self):
            self.is_connected = True
            raise TimeoutError("handshake timed out")
        async def disconnect(self):
            self.is_connected = False
            self.disconnected = True

    monkeypatch.setattr("explorer.manager.BluettiClient", BrokenClient)
    manager = Explorer()
    manager.selected = {"address": "AA", "encrypted": True}
    manager.client = SimpleNamespace(is_connected=True, disconnect=async_disconnect)
    result = await manager.start_telemetry()
    assert not result["connected"] and not result["telemetry"]
    assert "handshake timed out" in result["error"]
    assert instances[0].disconnected
    assert result["history"] == []


async def async_disconnect():
    pass


@pytest.mark.asyncio
async def test_invalid_soc_rejected():
    manager = Explorer()
    class Device:
        async def poll(self):
            return {"battery_soc": 65535}
    manager.device = Device()
    with pytest.raises(ValueError, match="SOC"):
        await manager._sample()
    assert not manager.history


@pytest.mark.asyncio
async def test_poll_failure_stops_and_disconnects(monkeypatch):
    manager = Explorer()
    class Client:
        is_connected = True
        async def disconnect(self):
            self.is_connected = False
    class Device:
        async def poll(self):
            raise RuntimeError("radio lost")
    async def no_sleep(seconds):
        return
    monkeypatch.setattr("explorer.manager.asyncio.sleep", no_sleep)
    manager.client, manager.device = Client(), Device()
    manager.telemetry = True
    await manager._poll()
    assert not manager.connected and not manager.telemetry
    assert "radio lost" in manager.error


@pytest.mark.asyncio
async def test_non_readable_gatt_rejected_without_io():
    manager = Explorer(demo=True)
    manager.demo_connected = True
    manager.services = [{"characteristics": [{"handle": 1, "properties": ["write"]}]}]
    with pytest.raises(ValueError, match="no permite"):
        await manager.read_characteristic(1)


@pytest.mark.asyncio
async def test_real_adapter_flow_with_fake_radio(monkeypatch):
    dev = SimpleNamespace(address="AA:BB", name="EL100V2")
    adv = SimpleNamespace(local_name=None, manufacturer_data={1: b"BLUETTE"}, rssi=-35, service_uuids=[])
    characteristic = SimpleNamespace(uuid="readable", handle=7, properties=["read"])
    service = SimpleNamespace(uuid="service", description="Battery", characteristics=[characteristic])
    class Scanner:
        @staticmethod
        async def discover(**kwargs):
            return {"AA:BB": (dev, adv)}
    class Client:
        def __init__(self, address, **kwargs):
            assert address == "AA:BB"
            self.is_connected = False
            self.services = [service]
        async def connect(self):
            self.is_connected = True
        async def disconnect(self):
            self.is_connected = False
        async def read_gatt_char(self, handle):
            assert handle == 7
            return bytearray(b"hello")
    monkeypatch.setattr("explorer.manager.BleakScanner", Scanner)
    monkeypatch.setattr("explorer.manager.BleakClient", Client)
    manager = Explorer(demo=False)
    assert (await manager.scan())[0]["encrypted"]
    state = await manager.connect("AA:BB")
    assert state["connected"] and state["services"][0]["description"] == "Battery"
    assert await manager.read_characteristic(7) == {"hex": "68656c6c6f", "text": "hello"}
    await manager.disconnect()
    assert not manager.connected


@pytest.mark.asyncio
async def test_plain_transport_reassembles_fragments_and_checks_count():
    from bluetti_monitor.client import BluettiClient
    from bluetti_monitor.crc import append_crc
    client = BluettiClient("AA")
    async def reply(command):
        frame = append_crc(bytes([1, 3, 4, 0, 76, 0, 22]))
        client._notify(None, frame[:2])
        client._notify(None, frame[2:])
    client._raw_write = reply
    response = await client.read_registers(100, 2)
    assert response.registers == [76, 22]


@pytest.mark.asyncio
async def test_official_sdk_encrypts_and_decrypts_without_embedded_keys():
    from bluetti_monitor.client import BluettiClient
    from bluetti_monitor.crc import append_crc
    client = BluettiClient("AA", encrypted=True)
    calls = []
    class SDK:
        def encrypt_data(self, data):
            calls.append("encrypt")
            return b"wrapped" + data
        def decrypt_data(self, data):
            calls.append("decrypt")
            return data[7:]
    client._sdk = SDK()
    client._ready.set()
    async def reply(command):
        assert command.startswith(b"wrapped")
        client._notify(None, b"wrapped" + append_crc(bytes([1, 3, 2, 0, 76])))
    client._raw_write = reply
    assert (await client.read_registers(100, 1)).registers == [76]
    assert calls == ["encrypt", "decrypt"]


def test_official_sdk_handshake_completion():
    from bluetti_monitor.client import BluettiClient
    client = BluettiClient("AA", encrypted=True)
    class SDK:
        def ble_crypt_link_handler(self, data):
            assert data == b"hello"
            return b"", 4
    client._sdk = SDK()
    client._notify(None, b"hello")
    assert client._ready.is_set()


@pytest.mark.asyncio
async def test_encrypted_mode_reports_missing_sdk(monkeypatch):
    from bluetti_monitor.client import BluettiClient, BluettiClientError
    def unavailable(name):
        raise ImportError("missing")
    monkeypatch.setattr("bluetti_monitor.client.importlib.import_module", unavailable)
    with pytest.raises(BluettiClientError, match="módulo oficial"):
        await BluettiClient("AA", encrypted=True).connect()
