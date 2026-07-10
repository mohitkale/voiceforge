"""Cached engine readiness — avoids heavy probes on every /healthz and /engines."""

from __future__ import annotations

import asyncio
import logging

from app.engines.registry import is_engine_enabled, list_engines

logger = logging.getLogger("voiceforge.readiness")

_ready: dict[str, bool] = {}
_counts: tuple[int, int] | None = None


def refresh_readiness() -> None:
    global _counts
    _ready.clear()
    engine_list = list_engines()
    for engine in engine_list:
        configured = is_engine_enabled(engine.id)
        _ready[engine.id] = configured and engine.is_ready()
    ready_count = sum(1 for engine_id, ok in _ready.items() if ok)
    _counts = (ready_count, len(engine_list))


def is_engine_ready_cached(engine_id: str) -> bool:
    if engine_id not in _ready:
        refresh_readiness()
    return _ready.get(engine_id, False)


def get_health_counts() -> tuple[int, int]:
    if _counts is None:
        refresh_readiness()
    assert _counts is not None
    return _counts


async def warmup_engines(engine_ids: list[str]) -> None:
    if not engine_ids:
        return
    from app.engines.registry import get_engine

    for engine_id in engine_ids:
        if not is_engine_enabled(engine_id):
            continue
        try:
            engine = get_engine(engine_id)
            if engine_id == "chatterbox":
                from app.engines.chatterbox_daemon import ensure_chatterbox_daemon

                await ensure_chatterbox_daemon()
            elif hasattr(engine, "_ensure_loaded"):
                await engine._ensure_loaded()
            logger.info("Warmup complete for engine %s", engine_id)
        except Exception:
            logger.warning("Warmup failed for engine %s", engine_id, exc_info=True)
    refresh_readiness()


async def start_warmup(engine_ids: list[str]) -> None:
    if not engine_ids:
        refresh_readiness()
        return
    asyncio.create_task(warmup_engines(engine_ids))
