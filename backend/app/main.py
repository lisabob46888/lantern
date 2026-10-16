"""Lantern backend entry point: `uvicorn app.main:app --port 8910` from backend/."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import scheduler
from app.api import core, stream
from app.store import db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.conn()
    if os.getenv("LANTERN_NO_POLLERS") != "1":
        scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(title="Lantern", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5899", "http://127.0.0.1:5899"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(core.router)
app.include_router(stream.router)

for name in ("companies", "industries"):
    try:
        mod = __import__(f"app.api.{name}", fromlist=["router"])
        app.include_router(mod.router)
    except ModuleNotFoundError:
        pass


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


if DIST.exists():  # serve the built frontend from the same process
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        f = DIST / path
        return FileResponse(f if f.is_file() else DIST / "index.html")
