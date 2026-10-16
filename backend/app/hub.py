"""Live hub: in-process pub/sub with sequence numbers and a 15-minute replay buffer.

`publish()` is safe to call from worker threads; delivery happens on the event loop.
"""
from __future__ import annotations

import asyncio
import itertools
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

REPLAY_SECONDS = 15 * 60


@dataclass(eq=False)  # identity hashing: subscribers live in a set
class Subscriber:
    queue: asyncio.Queue
    channels: set[str] = field(default_factory=set)

    def wants(self, ch: str) -> bool:
        # "wire:*" style prefixes and exact names are both allowed.
        return ch in self.channels or any(c.endswith("*") and ch.startswith(c[:-1]) for c in self.channels)


class Hub:
    def __init__(self) -> None:
        self._seq = itertools.count(1)
        self._buf: deque[dict] = deque(maxlen=20000)
        self._subs: set[Subscriber] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, ch: str, typ: str, data: Any) -> None:
        msg = {"seq": next(self._seq), "ts": int(time.time() * 1000), "ch": ch, "type": typ, "data": data}
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._deliver, msg)

    def _deliver(self, msg: dict) -> None:
        self._buf.append(msg)
        cutoff = msg["ts"] - REPLAY_SECONDS * 1000
        while self._buf and self._buf[0]["ts"] < cutoff:
            self._buf.popleft()
        for s in list(self._subs):
            if s.wants(msg["ch"]):
                try:
                    s.queue.put_nowait(msg)
                except asyncio.QueueFull:  # slow client: drop it, it will resume by seq
                    self._subs.discard(s)

    def subscribe(self, channels: set[str]) -> Subscriber:
        s = Subscriber(asyncio.Queue(maxsize=2000), set(channels))
        self._subs.add(s)
        return s

    def unsubscribe(self, s: Subscriber) -> None:
        self._subs.discard(s)

    def replay(self, s: Subscriber, after_seq: int) -> list[dict] | None:
        """Messages after `after_seq` for this subscriber, or None if the gap is older than the buffer."""
        if not self._buf:
            return []
        if after_seq < self._buf[0]["seq"] - 1:
            return None
        return [m for m in self._buf if m["seq"] > after_seq and s.wants(m["ch"])]


hub = Hub()
