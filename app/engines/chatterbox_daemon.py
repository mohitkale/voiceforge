"""Long-lived Chatterbox worker — keeps the model loaded between synth requests."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app.config import get_settings
from app.engines.base import EngineError
from app.engines.subprocess_env import sanitized_subprocess_env, worker_exec_command
from app.runtime_device import resolve_torch_device

logger = logging.getLogger("voiceforge.engines.chatterbox_daemon")

_WORKER_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "chatterbox_worker.py"


def resolve_chatterbox_python() -> Path | None:
    settings = get_settings()
    if settings.chatterbox_python:
        path = Path(settings.chatterbox_python)
        return path if path.is_file() else None
    default = Path("/opt/chatterbox-venv/bin/python")
    if default.is_file():
        return default
    return None


def resolve_chatterbox_model_dir() -> Path | None:
    settings = get_settings()
    if settings.chatterbox_model_dir:
        path = Path(settings.chatterbox_model_dir)
        return path if path.is_dir() else None
    default = settings.models_dir / "chatterbox"
    return default if default.is_dir() else None

_proc: asyncio.subprocess.Process | None = None
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _resolve_device() -> str:
    return resolve_torch_device(get_settings().device)


async def _read_line(proc: asyncio.subprocess.Process) -> str:
    assert proc.stdout is not None
    line = await proc.stdout.readline()
    return line.decode(errors="replace").rstrip()


async def _drain_until_ready(proc: asyncio.subprocess.Process, timeout_s: float = 300.0) -> None:
    async def _loop() -> None:
        while True:
            text = await _read_line(proc)
            if not text:
                raise EngineError("Chatterbox worker exited during startup")
            if text.startswith('{"type":'):
                evt = json.loads(text)
                if evt.get("type") == "progress" and evt.get("message") == "ready":
                    return
                if evt.get("type") == "error":
                    raise EngineError(str(evt.get("message", "Chatterbox worker startup failed")))
            elif text == "ok":
                continue
            logger.info("[chatterbox-daemon] %s", text)

    await asyncio.wait_for(_loop(), timeout=timeout_s)


async def ensure_chatterbox_daemon() -> None:
    global _proc
    async with _get_lock():
        if _proc is not None and _proc.returncode is None:
            return

        python = resolve_chatterbox_python()
        model_dir = resolve_chatterbox_model_dir()
        if python is None or model_dir is None or not _WORKER_SCRIPT.is_file():
            raise EngineError("Chatterbox worker is not configured")

        device = _resolve_device()
        cmd = worker_exec_command(
            python,
            _WORKER_SCRIPT,
            [
                "serve",
                "--device",
                device,
                "--model-dir",
                str(model_dir),
                "--t3-model",
                "v3",
            ],
        )
        logger.info("Starting Chatterbox daemon: %s", " ".join(cmd))
        _proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=sanitized_subprocess_env(),
        )
        await _drain_until_ready(_proc)


async def synthesize_via_daemon(
    *,
    ref_audio: Path,
    text: str,
    output: Path,
    language: str,
) -> None:
    global _proc
    await ensure_chatterbox_daemon()
    assert _proc is not None and _proc.stdin is not None

    payload = json.dumps(
        {
            "cmd": "synthesize",
            "ref_audio": str(ref_audio),
            "text": text,
            "output": str(output),
            "language": language,
        }
    )
    async with _get_lock():
        if _proc.returncode is not None:
            _proc = None
            await ensure_chatterbox_daemon()
        assert _proc is not None and _proc.stdin is not None
        _proc.stdin.write((payload + "\n").encode())
        await _proc.stdin.drain()

        while True:
            text_line = await _read_line(_proc)
            if not text_line:
                _proc = None
                raise EngineError("Chatterbox worker exited during synthesis")
            if not text_line.startswith('{"type":'):
                logger.info("[chatterbox-daemon] %s", text_line)
                continue
            evt = json.loads(text_line)
            if evt.get("type") == "progress" and evt.get("message") == "done":
                return
            if evt.get("type") == "error":
                raise EngineError(str(evt.get("message", "Chatterbox synthesis failed")))
