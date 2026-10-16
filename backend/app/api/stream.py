"""WebSocket stream. Client frames:
  {"op": "sub", "channels": ["wire", "quotes", "story:<id>", "report:*"], "after": <last seq or 0>}
Server frames are hub messages: {"seq", "ts", "ch", "type", "data"}, plus {"type": "resync"} when
the client's last seq is older than the replay buffer (it should refetch snapshots).
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.hub import hub

router = APIRouter()


@router.websocket("/api/v1/stream")
async def stream(ws: WebSocket) -> None:
    await ws.accept()
    sub = hub.subscribe(set())
    try:
        async def reader() -> None:
            while True:
                msg = json.loads(await ws.receive_text())
                if msg.get("op") == "sub":
                    sub.channels |= set(msg.get("channels") or [])
                    after = int(msg.get("after") or 0)
                    if after:
                        missed = hub.replay(sub, after)
                        if missed is None:
                            await ws.send_text(json.dumps({"type": "resync"}))
                        else:
                            for m in missed:
                                await ws.send_text(json.dumps(m, ensure_ascii=False))
                elif msg.get("op") == "unsub":
                    sub.channels -= set(msg.get("channels") or [])
                elif msg.get("op") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))

        async def writer() -> None:
            while True:
                m = await sub.queue.get()
                await ws.send_text(json.dumps(m, ensure_ascii=False))

        done, pending = await asyncio.wait({asyncio.create_task(reader()), asyncio.create_task(writer())},
                                           return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in done:
            if t.exception() and not isinstance(t.exception(), WebSocketDisconnect):
                raise t.exception()
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(sub)
