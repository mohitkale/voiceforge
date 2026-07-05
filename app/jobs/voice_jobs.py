"""Background processing for voice creation: runs the (potentially slow)
engine work outside the request/response cycle, updates the DB, and streams
progress over the in-process event bus (-> SSE).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import Session

from app.db import engine as db_engine
from app.db_models import Voice, VoiceStatus
from app.engines.base import EngineError
from app.engines.registry import get_engine
from app.jobs.events_bus import VoiceEvent, get_event_bus
from app.metrics import get_metrics
from app.security import get_job_limiter
from app.storage import preview_path

logger = logging.getLogger("voiceforge.jobs")

_PREVIEW_TEXT = "Hello — this is a preview of this cloned voice."


async def run_create_voice(voice_id: str, sample_paths: list[str], language: str) -> None:
    bus = get_event_bus()

    async def on_progress(message: str, extra: dict | None = None) -> None:
        await bus.publish(voice_id, VoiceEvent(type="progress", message=message, extra=extra))

    async with get_job_limiter():
        with Session(db_engine) as session:
            voice = session.get(Voice, voice_id)
            if voice is None:
                logger.error("Voice %s vanished before processing started", voice_id)
                return
            engine_id, tier = voice.engine_id, voice.tier

        try:
            clone_engine = get_engine(engine_id)
            from pathlib import Path

            artifact = await clone_engine.create_voice(
                voice_id=voice_id,
                sample_paths=[Path(p) for p in sample_paths],
                tier=tier,
                language=language,
                on_progress=on_progress,
            )

            preview_bytes: bytes | None = None
            try:
                from app.engines.base import SynthesizeOptions

                preview_bytes = await clone_engine.synthesize(
                    voice_id=voice_id,
                    artifact=artifact,
                    text=_PREVIEW_TEXT,
                    opts=SynthesizeOptions(language=language),
                )
            except Exception:  # noqa: BLE001
                logger.warning("Preview generation failed for voice %s", voice_id, exc_info=True)

            with Session(db_engine) as session:
                voice = session.get(Voice, voice_id)
                if voice is None:
                    return
                voice.status = VoiceStatus.ready
                voice.artifact = artifact.model_dump()
                voice.ready_at = datetime.now(UTC)
                voice.updated_at = voice.ready_at
                session.add(voice)
                session.commit()

            if preview_bytes:
                preview_path(voice_id).write_bytes(preview_bytes)

            get_metrics().inc("voices_ready")

            await bus.publish(
                voice_id, VoiceEvent(type="status", message="ready", extra={"status": "ready"})
            )

        except EngineError as exc:
            get_metrics().inc("voices_failed")
            _mark_failed(voice_id, str(exc))
            await _publish_failed(bus, voice_id, str(exc))
        except Exception as exc:  # noqa: BLE001 - never let a bug hang a voice in "processing"
            logger.exception("Unexpected error processing voice %s", voice_id)
            get_metrics().inc("voices_failed")
            _mark_failed(voice_id, "Internal error while processing this voice")
            await _publish_failed(bus, voice_id, str(exc))


async def _publish_failed(bus, voice_id: str, error: str) -> None:
    extra = {"status": "failed", "error": error}
    await bus.publish(voice_id, VoiceEvent(type="status", message="failed", extra=extra))


def _mark_failed(voice_id: str, message: str) -> None:
    with Session(db_engine) as session:
        voice = session.get(Voice, voice_id)
        if voice is None:
            return
        voice.status = VoiceStatus.failed
        voice.error_message = message
        voice.updated_at = datetime.now(UTC)
        session.add(voice)
        session.commit()
