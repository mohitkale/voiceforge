"""Chatterbox Multilingual V3 — MIT zero-shot cloning via an isolated worker.

``chatterbox-tts`` pins numpy&lt;2 and older torch, which conflict with
coqui-tts in the main VoiceForge venv. Inference runs under
``VOICEFORGE_CHATTERBOX_PYTHON`` (default ``/opt/chatterbox-venv/bin/python``).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from app.config import get_settings
from app.engines.asr import pick_longest_sample
from app.engines.base import (
    CloneCapabilities,
    EngineError,
    ProgressFn,
    SynthesizeOptions,
    Tier,
    VoiceArtifact,
)
from app.engines.chatterbox_daemon import synthesize_via_daemon
from app.engines.wav_output import to_wav_bytes
from app.engines.worker_client import ping_worker
from app.storage import artifacts_dir

logger = logging.getLogger("voiceforge.engines.chatterbox")

_WORKER_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "chatterbox_worker.py"
CHATTERBOX_NATIVE_SAMPLE_RATE = 24000

SUPPORTED_LANGUAGES = [
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja",
    "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh",
]


def resolve_chatterbox_python() -> Path | None:
    settings = get_settings()
    if settings.chatterbox_python:
        path = Path(settings.chatterbox_python)
        return path if path.is_file() else None
    default = Path("/opt/chatterbox-venv/bin/python")
    if default.is_file():
        return default
    return None


def chatterbox_worker_configured() -> bool:
    return (
        resolve_chatterbox_python() is not None
        and resolve_chatterbox_model_dir() is not None
        and _WORKER_SCRIPT.is_file()
    )


def resolve_chatterbox_model_dir() -> Path | None:
    settings = get_settings()
    if settings.chatterbox_model_dir:
        path = Path(settings.chatterbox_model_dir)
        return path if path.is_dir() else None
    default = settings.models_dir / "chatterbox"
    return default if default.is_dir() else None


class ChatterboxEngine:
    id = "chatterbox"
    label = "Chatterbox Multilingual V3"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=5.0,
        recommended_sample_seconds=10.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=False,
        license="MIT (Resemble AI Chatterbox)",
        approx_vram_gb=4.0,
    )

    def is_ready(self) -> bool:
        return chatterbox_worker_configured()

    async def create_voice(
        self,
        voice_id: str,
        sample_paths: list[Path],
        tier: Tier,
        language: str,
        on_progress: ProgressFn | None = None,
    ) -> VoiceArtifact:
        if not sample_paths:
            raise EngineError("At least one reference sample is required")
        if not chatterbox_worker_configured():
            raise EngineError(
                "Chatterbox worker is not configured — set "
                "VOICEFORGE_CHATTERBOX_PYTHON to an interpreter with "
                "chatterbox-tts installed and VOICEFORGE_CHATTERBOX_MODEL_DIR "
                "to an explicitly downloaded local model snapshot"
            )
        normalized_language = (language or "en").split("-")[0].lower()
        if normalized_language not in SUPPORTED_LANGUAGES:
            raise EngineError(
                f"Language '{language}' is not supported by Chatterbox Multilingual V3"
            )

        async def report(msg: str, extra: dict | None = None) -> None:
            if on_progress:
                await on_progress(msg, extra)

        await report("caching_reference")
        ref_source = pick_longest_sample(sample_paths)
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_audio = out_dir / "chatterbox_ref.wav"
        shutil.copy2(ref_source, ref_audio)

        await report("done")
        settings = get_settings()
        return VoiceArtifact(
            engine_id=self.id,
            tier=tier,
            data={
                "ref_audio_path": str(ref_audio.relative_to(settings.data_dir)),
                "language": language,
            },
        )

    async def synthesize(
        self,
        voice_id: str,
        artifact: VoiceArtifact,
        text: str,
        opts: SynthesizeOptions,
    ) -> bytes:
        python = resolve_chatterbox_python()
        if python is None:
            raise EngineError("VOICEFORGE_CHATTERBOX_PYTHON is not configured")

        ref_rel = artifact.data.get("ref_audio_path")
        if not ref_rel:
            raise EngineError("Voice is missing Chatterbox reference audio")

        ref_path = get_settings().data_dir / ref_rel
        if not ref_path.exists():
            raise EngineError("Cached reference audio is missing on disk")

        out_wav = artifacts_dir(voice_id) / "chatterbox_last.wav"

        await synthesize_via_daemon(
            ref_audio=ref_path,
            text=text,
            output=out_wav,
            language=(opts.language or artifact.data.get("language") or "en").split("-")[0],
        )

        if not out_wav.is_file():
            raise EngineError("Chatterbox worker did not produce output audio")

        wav, sr = sf.read(str(out_wav), dtype="float32", always_2d=False)
        if getattr(wav, "ndim", 1) > 1:
            wav = wav.mean(axis=1)
        target_rate = opts.sample_rate or 44100
        return to_wav_bytes(
            np.asarray(wav, dtype=np.float32),
            source_rate=int(sr) or CHATTERBOX_NATIVE_SAMPLE_RATE,
            target_rate=target_rate,
        )


async def ensure_chatterbox_ready() -> None:
    python = resolve_chatterbox_python()
    if python is None:
        raise EngineError("Chatterbox worker Python not configured")
    if not await ping_worker(python=python, script=_WORKER_SCRIPT, label="chatterbox"):
        raise EngineError("Chatterbox worker ping failed")
