"""A tiny in-process pub/sub for per-voice SSE progress events.

Deliberately not backed by Redis/etc: this is a single-process, single-user,
local-first service (see brief §7) — an `asyncio.Queue` per subscriber is
enough and adds zero operational surface.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field


@dataclass
class VoiceEvent:
    type: str
    message: str
    extra: dict | None = None
    ts: float = field(default_factory=time.time)

    def to_sse_dict(self) -> dict:
        payload = {"type": self.type, "message": self.message, "ts": self.ts}
        if self.extra:
            payload.update(self.extra)
        return payload


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, voice_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.setdefault(voice_id, set()).add(q)
        return q

    async def unsubscribe(self, voice_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            subs = self._subscribers.get(voice_id)
            if subs is not None:
                subs.discard(q)
                if not subs:
                    self._subscribers.pop(voice_id, None)

    async def publish(self, voice_id: str, event: VoiceEvent) -> None:
        async with self._lock:
            subs = list(self._subscribers.get(voice_id, ()))
        for q in subs:
            if q.full():
                # Drop the oldest event rather than block the publisher
                # (progress updates are best-effort, never business data).
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait(event)


_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus
