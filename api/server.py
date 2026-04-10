from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

LOGGER = logging.getLogger("autonomous_fighter.api")

_clients: Set[WebSocket] = set()
_main_loop: asyncio.AbstractEventLoop | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    yield


app = FastAPI(title="AutonomousFighter Telemetry API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/stats")
async def stats() -> Dict[str, int]:
    return {"connected_clients": len(_clients)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    LOGGER.info("WebSocket connected. clients=%d", len(_clients))
    try:
        while True:
            message = await websocket.receive_text()
            if message.lower() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(websocket)
        LOGGER.info("WebSocket disconnected. clients=%d", len(_clients))


async def broadcast(packet: Dict[str, Any]) -> None:
    dead_clients = []
    for client in _clients:
        try:
            await client.send_json(packet)
        except Exception:
            dead_clients.append(client)

    for client in dead_clients:
        _clients.discard(client)


def broadcast_sync(packet: Dict[str, Any]) -> None:
    if _main_loop is None:
        return
    
    try:
        if _main_loop.is_closed():
            return
        
        if not _main_loop.is_running():
            return
            
        future = asyncio.run_coroutine_threadsafe(broadcast(packet), _main_loop)
        with contextlib.suppress(Exception):
            future.result(timeout=0.05)
    except RuntimeError:
        # Event loop is closed or in invalid state
        return
    except Exception:
        # Suppress any other errors
        return
