"""Read-only control panel for factory runs.

Run:  uvicorn dashboard.server:app --port 8001
Then open http://127.0.0.1:8001 and start ./factory.sh <n> in a terminal.

The panel only watches .factory/ (or $FACTORY_DIR). It never starts, stops or
changes a run, so if it breaks on stage the terminal still has everything.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse

from dashboard.state import build_state

ROOT = Path(__file__).resolve().parent.parent
INDEX = Path(__file__).resolve().parent / "index.html"
POLL_SECONDS = 0.4
HEARTBEAT_SECONDS = 15.0

app = FastAPI(title="Factory dashboard")


class Disconnectable(Protocol):
    async def is_disconnected(self) -> bool: ...


def factory_dir() -> Path:
    return Path(os.environ.get("FACTORY_DIR", ROOT / ".factory")).resolve()


def snapshot() -> dict[str, Any]:
    return build_state(factory_dir(), root=f"{ROOT}/")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX, media_type="text/html")


@app.get("/api/state")
def state() -> dict[str, Any]:
    return snapshot()


async def state_events(request: Disconnectable) -> AsyncIterator[str]:
    """Server-sent events: the full state whenever it changes, a comment ping otherwise."""
    last, idle = "", 0.0
    while not await request.is_disconnected():
        body = json.dumps(await asyncio.to_thread(snapshot))
        if body != last:
            last, idle = body, 0.0
            yield f"data: {body}\n\n"
        elif idle >= HEARTBEAT_SECONDS:
            idle = 0.0
            yield ": ping\n\n"
        await asyncio.sleep(POLL_SECONDS)
        idle += POLL_SECONDS


@app.get("/api/stream")
async def stream(request: Request) -> StreamingResponse:
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(state_events(request), media_type="text/event-stream", headers=headers)
