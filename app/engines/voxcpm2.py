"""VoxCPM2 experimental clone provider through an opt-in isolated worker."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from app.config import get_settings
from app.engines.asr import map_asr_language, pick_longest_sample, transcribe_reference_audio
from app.engines.base import (
    CloneCapabilities,
    EngineError,
    ProgressFn,
    SynthesizeOptions,
    Tier,
    VoiceArtifact,
)
from app.engines.wav_output import to_wav_bytes
from app.engines.worker_client import run_worker
from app.runtime_device import resolve_torch_device
from app.storage import artifacts_dir

logger = logging.getLogger("voiceforge.engines.voxcpm2")

_WORKER_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "voxcpm2_worker.py"
VOXCPM2_NATIVE_SAMPLE_RATE = 48000
SUPPORTED_LANGUAGES = [
    "ar", "my", "zh", "da", "nl", "en", "fi", "fr", "de", "el", "he", "hi", "id", "it",
    "ja", "km", "ko", "lo", "ms", "no", "pl", "pt", "ru", "es", "sw", "sv", "tl", "th",
    "tr", "vi",
]


def resolve_voxcpm2_python() -> Path | None:
    settings = get_settings()
    if settings.voxcpm2_python:
        path = Path(settings.voxcpm2_python)
        return path if path.is_file() else None
    default = Path("/opt/voxcpm2-venv/bin/python")
    return default if default.is_file() else None


def resolve_voxcpm2_model_dir() -> Path | None:
    settings = get_settings()
    if settings.voxcpm2_model_dir:
        path = Path(settings.voxcpm2_model_dir)
        return path if path.is_dir() else None
    default = settings.models_dir / "voxcpm2"
    return default if default.is_dir() else None


class VoxCpm2Engine:
    id = "voxcpm2"
    label = "VoxCPM2 (experimental, opt-in)"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=3.0,
        recommended_sample_seconds=10.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=False,
        license="Apache-2.0 (VoxCPM2)",
        approx_vram_gb=8.0,
    )

    def is_ready(self) -> bool:
        return (
            resolve_voxcpm2_python() is not None
            and resolve_voxcpm2_model_dir() is not None
            and _WORKER_SCRIPT.is_file()
        )

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
        normalized_language = (language or "en").split("-")[0].lower()
        if normalized_language not in SUPPORTED_LANGUAGES:
            raise EngineError(f"Language '{language}' is not supported by VoxCPM2")

        async def report(message: str, extra: dict | None = None) -> None:
            if on_progress:
                await on_progress(message, extra)

        await report("caching_reference")
        source = pick_longest_sample(sample_paths)
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_audio = out_dir / "voxcpm2_ref.wav"
        shutil.copy2(source, ref_audio)

        ref_text = ""
        if tier == "high_fidelity":
            await report("transcribing_reference")

            def _transcribe() -> str:
                return transcribe_reference_audio(
                    ref_audio,
                    language=map_asr_language(normalized_language),
                    device=resolve_torch_device(get_settings().device),
                )

            try:
                ref_text = await asyncio.get_running_loop().run_in_executor(None, _transcribe)
            except Exception as exc:
                logger.warning("VoxCPM2 reference transcription failed: %s", exc)

        await report("done")
        return VoiceArtifact(
            engine_id=self.id,
            tier=tier,
            data={
                "ref_audio_path": str(ref_audio.relative_to(get_settings().data_dir)),
                "ref_text": ref_text,
                "language": normalized_language,
            },
        )

    async def synthesize(
        self,
        voice_id: str,
        artifact: VoiceArtifact,
        text: str,
        opts: SynthesizeOptions,
    ) -> bytes:
        python = resolve_voxcpm2_python()
        model_dir = resolve_voxcpm2_model_dir()
        if python is None or model_dir is None:
            raise EngineError(
                "VoxCPM2 is not configured; set VOICEFORGE_VOXCPM2_PYTHON and "
                "VOICEFORGE_VOXCPM2_MODEL_DIR to an isolated worker and local snapshot"
            )
        ref_rel = artifact.data.get("ref_audio_path")
        if not ref_rel:
            raise EngineError("Voice is missing VoxCPM2 reference audio")
        ref_path = get_settings().data_dir / ref_rel
        if not ref_path.is_file():
            raise EngineError("Cached VoxCPM2 reference audio is missing")

        out_wav = artifacts_dir(voice_id) / "voxcpm2_last.wav"
        args = [
            "synthesize",
            "--model-dir",
            str(model_dir),
            "--ref-audio",
            str(ref_path),
            "--text",
            text,
            "--output",
            str(out_wav),
            "--device",
            resolve_torch_device(get_settings().device),
            "--seed",
            "42",
        ]
        ref_text = artifact.data.get("ref_text")
        if ref_text:
            args.extend(["--ref-text", str(ref_text)])
        if opts.style:
            args.extend(["--style", opts.style])

        await run_worker(
            python=python,
            script=_WORKER_SCRIPT,
            args=args,
            label="voxcpm2",
            timeout_s=900,
        )
        if not out_wav.is_file():
            raise EngineError("VoxCPM2 worker did not produce output audio")
        wav, source_rate = sf.read(str(out_wav), dtype="float32", always_2d=False)
        if getattr(wav, "ndim", 1) > 1:
            wav = wav.mean(axis=1)
        return to_wav_bytes(
            np.asarray(wav, dtype=np.float32),
            source_rate=int(source_rate) or VOXCPM2_NATIVE_SAMPLE_RATE,
            target_rate=opts.sample_rate or 44100,
        )

