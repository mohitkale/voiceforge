"""Generic subprocess client for isolated engine workers.

Used by CosyVoice 3 and IndexTTS2 (same JSON-progress protocol as RVC).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from app.engines.base import EngineError, ProgressFn

logger = logging.getLogger("voiceforge.engines.worker_client")


async def run_worker(
    *,
    python: Path,
    script: Path,
    args: Sequence[str],
    label: str,
    on_progress: ProgressFn | None = None,
    timeout_s: float | None = None,
) -> str:
    if not python.is_file():
        raise EngineError(f"{label} worker Python not found: {python}")
    if not script.is_file():
        raise EngineError(f"{label} worker script not found: {script}")

    cmd = [str(python), str(script), *args]
    logger.info("Starting %s worker: %s", label, " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def _read_stdout() -> str:
        assert proc.stdout is not None
        tail: list[str] = []
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            if text.startswith('{"type":'):
                try:
                    evt = json.loads(text)
                except json.JSONDecodeError:
                    logger.info("[%s-worker] %s", label, text)
                    continue
                if evt.get("type") == "progress" and on_progress:
                    await on_progress(evt.get("message", ""), evt.get("extra"))
                elif evt.get("type") == "error":
                    tail.append(str(evt.get("message", f"{label} worker error")))
                continue
            logger.info("[%s-worker] %s", label, text)
            tail.append(text)
            if len(tail) > 20:
                tail.pop(0)
        return "\n".join(tail)

    try:
        if timeout_s is None:
            tail = await _read_stdout()
            await proc.wait()
        else:
            tail = await asyncio.wait_for(_read_stdout(), timeout=timeout_s)
            await proc.wait()
    except TimeoutError as exc:
        proc.kill()
        raise EngineError(f"{label} worker timed out after {timeout_s:.0f}s") from exc

    if proc.returncode != 0:
        detail = tail.strip() or f"exit code {proc.returncode}"
        raise EngineError(f"{label} worker failed: {detail}")
    return tail


async def ping_worker(*, python: Path, script: Path, label: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            str(python),
            str(script),
            "ping",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        return proc.returncode == 0 and b"ok" in (stdout or b"")
    except Exception:
        logger.debug("%s worker ping failed", label, exc_info=True)
        return False
