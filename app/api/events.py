from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session
from starlette.responses import StreamingResponse

from app.db import get_session
from app.db_models import Voice
from app.jobs.events_bus import get_event_bus
from app.security import auth_dependency

router = APIRouter(prefix="/v1/voices", tags=["events"], dependencies=[Depends(auth_dependency)])

_HEARTBEAT_SECONDS = 15.0


@router.get("/{voice_id}/events")
async def voice_events(voice_id: str, request: Request, session: Session = Depends(get_session)):
    voice = session.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice not found")

    bus = get_event_bus()
    queue = await bus.subscribe(voice_id)

    async def stream():
        try:
            # Replay current status immediately so a client connecting after
            # processing already finished still gets a terminal event.
            yield _sse(
                "status",
                {"status": voice.status.value, "message": voice.status.value},
            )
            if voice.status.value in ("ready", "failed"):
                return

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield _sse(event.type, event.to_sse_dict())
                if event.type == "status" and event.extra and event.extra.get("status") in (
                    "ready",
                    "failed",
                ):
                    break
        finally:
            await bus.unsubscribe(voice_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
