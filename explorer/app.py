import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .manager import Explorer

STATIC = Path(__file__).parent / "static"


class Connect(BaseModel):
    address: str = Field(min_length=1, max_length=200)


class Telemetry(BaseModel):
    encryption: str = "auto"


def create_app(demo=None):
    manager = Explorer(demo=os.getenv("BLUETTI_DEMO") == "1" if demo is None else demo)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await manager.disconnect()

    app = FastAPI(title="Bluetti Chisme", lifespan=lifespan)
    app.state.manager = manager
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def failure(request, exc):
        detail = f"{type(exc).__name__}: {str(exc)}. Comprueba Bluetooth, permisos y que la app del móvil esté cerrada."
        manager.log(detail)
        return JSONResponse({"detail": detail}, status_code=503)

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    async def state():
        return manager.snapshot()

    @app.post("/api/scan")
    async def scan():
        return await manager.scan()

    @app.post("/api/connect")
    async def connect(body: Connect):
        return await manager.connect(body.address)

    @app.post("/api/disconnect")
    async def disconnect():
        return await manager.disconnect()

    @app.post("/api/telemetry")
    async def telemetry(body: Telemetry):
        if body.encryption not in {"auto", "encrypted", "plain"}:
            raise HTTPException(400, "Modo de cifrado inválido")
        return await manager.start_telemetry(body.encryption)

    @app.post("/api/gatt/{handle}")
    async def read(handle: int):
        return await manager.read_characteristic(handle)

    @app.get("/api/export")
    async def export():
        return JSONResponse(manager.snapshot(), headers={"Content-Disposition": 'attachment; filename="bluetti-diagnostico.json"'})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
