"""Subprocess client for the isolated RVC worker (`scripts/rvc_worker.py`).

RVC's stack (fairseq, numpy<2, etc.) conflicts with coqui-tts in the main
VoiceForge venv, so training/inference run in a separate Python interpreter
(typically ``/opt/rvc-venv`` in the GPU Docker image).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.engines.base import EngineError, ProgressFn
from app.engines.subprocess_env import sanitized_subprocess_env, worker_exec_command

logger = logging.getLogger("voiceforge.engines.rvc_worker")

_WORKER_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rvc_worker.py"


def resolve_rvc_python() -> Path | None:
    settings = get_settings()
    if settings.rvc_python:
        path = Path(settings.rvc_python)
        return path if path.is_file() else None
    default = Path("/opt/rvc-venv/bin/python")
    if default.is_file():
        return default
    return None


def rvc_worker_configured() -> bool:
    return resolve_rvc_python() is not None and _WORKER_SCRIPT.is_file()


async def ping_worker() -> bool:
    python = resolve_rvc_python()
    if python is None:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            *worker_exec_command(python, _WORKER_SCRIPT, ["ping"]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=sanitized_subprocess_env(),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        return proc.returncode == 0 and b"ok" in (stdout or b"")
    except Exception:
        logger.debug("RVC worker ping failed", exc_info=True)
        return False


async def _run_worker(
    args: Sequence[str],
    *,
    on_progress: ProgressFn | None = None,
    timeout_s: float | None = None,
) -> None:
    python = resolve_rvc_python()
    if python is None:
        raise EngineError(
            "RVC worker is not configured — set VOICEFORGE_RVC_PYTHON to an "
            "interpreter with rvc-python installed (see README / GPU Docker image)"
        )

    cmd = worker_exec_command(python, _WORKER_SCRIPT, args)
    logger.info("Starting RVC worker: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=sanitized_subprocess_env(),
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
                    logger.info("[rvc-worker] %s", text)
                    continue
                if evt.get("type") == "progress" and on_progress:
                    await on_progress(evt.get("message", ""), evt.get("extra"))
                elif evt.get("type") == "error":
                    tail.append(str(evt.get("message", "RVC worker error")))
                continue
            logger.info("[rvc-worker] %s", text)
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
        raise EngineError(f"RVC worker timed out after {timeout_s:.0f}s") from exc

    if proc.returncode != 0:
        detail = tail.strip() or f"exit code {proc.returncode}"
        raise EngineError(f"RVC worker failed: {detail}")


async def setup_worker(*, on_progress: ProgressFn | None = None) -> None:
    await _run_worker(["setup"], on_progress=on_progress, timeout_s=3600.0)


async def train_model(
    *,
    work_dir: Path,
    model_name: str,
    sample_paths: Sequence[Path],
    epochs: int,
    batch_size: int,
    device: str,
    on_progress: ProgressFn | None = None,
) -> None:
    args = [
        "train",
        "--work-dir",
        str(work_dir),
        "--model-name",
        model_name,
        "--epochs",
        str(epochs),
        "--batch-size",
        str(batch_size),
        "--device",
        device,
        "--samples",
        *[str(p) for p in sample_paths],
    ]
    await _run_worker(args, on_progress=on_progress, timeout_s=None)


async def infer_file(
    *,
    model_path: Path,
    index_path: Path | None,
    input_path: Path,
    output_path: Path,
    device: str,
    version: str = "v2",
) -> None:
    args = [
        "infer",
        "--model",
        str(model_path),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--device",
        _rvc_device(device),
        "--version",
        version,
    ]
    if index_path and index_path.is_file():
        args.extend(["--index", str(index_path)])
    await _run_worker(args, timeout_s=1800.0)


def _rvc_device(device: str) -> str:
    if device.startswith("cuda"):
        return "cuda:0" if device == "cuda" else device
    return "cpu:0"


async def ensure_worker_ready() -> None:
    if not rvc_worker_configured():
        raise EngineError(
            "RVC is not configured on this host — install the RVC worker venv "
            "or use the GPU Docker image with /opt/rvc-venv"
        )
    if not await ping_worker():
        await setup_worker()
        if not await ping_worker():
            raise EngineError("RVC worker failed to start after setup")
