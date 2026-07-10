"""CosyVoice 3 engine — zero-shot cloning via an isolated worker venv.

Main app stays on Python 3.11 / coqui pins; CosyVoice runs under
``VOICEFORGE_COSYVOICE_PYTHON`` (default ``/opt/cosyvoice-venv/bin/python``).
"""

from __future__ import annotations

import asyncio
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
from app.engines.worker_client import ping_worker, run_worker
from app.storage import artifacts_dir

_WORKER_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cosyvoice_worker.py"
COSYVOICE_NATIVE_SAMPLE_RATE = 24000

SUPPORTED_LANGUAGES = [
    "zh", "en", "ja", "ko", "de", "es", "fr", "it", "ru",
]


def resolve_cosyvoice_python() -> Path | None:
    settings = get_settings()
    if settings.cosyvoice_python:
        path = Path(settings.cosyvoice_python)
        return path if path.is_file() else None
    default = Path("/opt/cosyvoice-venv/bin/python")
    if default.is_file():
        return default
    return None


def cosyvoice_worker_configured() -> bool:
    return resolve_cosyvoice_python() is not None and _WORKER_SCRIPT.is_file()


class CosyVoice3Engine:
    id = "cosyvoice-3"
    label = "CosyVoice 3 (Fun-CosyVoice3-0.5B)"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=3.0,
        recommended_sample_seconds=10.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=True,
        license="Apache-2.0 (Fun-CosyVoice 3.0)",
        approx_vram_gb=6.0,
    )

    def _resolve_device(self) -> str:
        settings = get_settings()
        if settings.device != "auto":
            return settings.device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def is_ready(self) -> bool:
        return cosyvoice_worker_configured()

    def _model_dir(self) -> Path:
        return get_settings().models_dir / "Fun-CosyVoice3-0.5B"

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
        if not cosyvoice_worker_configured():
            raise EngineError(
                "CosyVoice worker is not configured — set VOICEFORGE_COSYVOICE_PYTHON "
                "to an interpreter with CosyVoice installed"
            )

        async def report(msg: str, extra: dict | None = None) -> None:
            if on_progress:
                await on_progress(msg, extra)

        await report("caching_reference")
        ref_source = pick_longest_sample(sample_paths)
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_audio = out_dir / "cosyvoice_ref.wav"
        shutil.copy2(ref_source, ref_audio)

        await report("transcribing_reference")
        asr_language = map_asr_language(language, set(SUPPORTED_LANGUAGES))
        device = self._resolve_device()

        def _transcribe() -> str:
            text = transcribe_reference_audio(
                str(ref_audio),
                language=asr_language,
                device=device,
            )
            if not (text or "").strip():
                raise EngineError(
                    "Could not transcribe the reference audio — CosyVoice needs "
                    "prompt text; try a clearer clip"
                )
            return text.strip()

        loop = asyncio.get_running_loop()
        try:
            ref_text = await loop.run_in_executor(None, _transcribe)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Reference transcription failed: {exc}") from exc

        # Ensure checkpoints exist (best-effort; synthesize will fail clearly if missing).
        model_dir = self._model_dir()
        if not model_dir.exists():
            await report("downloading_model")
            python = resolve_cosyvoice_python()
            assert python is not None
            await run_worker(
                python=python,
                script=_WORKER_SCRIPT,
                args=["setup", "--models-dir", str(get_settings().models_dir)],
                label="cosyvoice",
                on_progress=on_progress,
                timeout_s=7200.0,
            )

        await report("done")
        settings = get_settings()
        return VoiceArtifact(
            engine_id=self.id,
            tier=tier,
            data={
                "ref_audio_path": str(ref_audio.relative_to(settings.data_dir)),
                "ref_text": ref_text,
                "language": language,
                "model_dir": str(model_dir),
            },
        )

    async def synthesize(
        self,
        voice_id: str,
        artifact: VoiceArtifact,
        text: str,
        opts: SynthesizeOptions,
    ) -> bytes:
        python = resolve_cosyvoice_python()
        if python is None:
            raise EngineError("VOICEFORGE_COSYVOICE_PYTHON is not configured")

        ref_rel = artifact.data.get("ref_audio_path")
        ref_text = artifact.data.get("ref_text") or ""
        if not ref_rel:
            raise EngineError("Voice is missing CosyVoice reference audio")

        ref_path = get_settings().data_dir / ref_rel
        if not ref_path.exists():
            raise EngineError("Cached reference audio is missing on disk")

        model_dir = Path(artifact.data.get("model_dir") or self._model_dir())
        out_wav = artifacts_dir(voice_id) / "cosyvoice_last.wav"
        prompt_text = (
            f"You are a helpful assistant.<|endofprompt|>{ref_text}"
            if ref_text
            else "You are a helpful assistant.<|endofprompt|>"
        )

        await run_worker(
            python=python,
            script=_WORKER_SCRIPT,
            args=[
                "synthesize",
                "--model-dir",
                str(model_dir),
                "--ref-audio",
                str(ref_path),
                "--ref-text",
                prompt_text,
                "--text",
                text,
                "--output",
                str(out_wav),
            ],
            label="cosyvoice",
            timeout_s=1800.0,
        )

        if not out_wav.is_file():
            raise EngineError("CosyVoice worker did not produce output audio")

        wav, sr = sf.read(str(out_wav), dtype="float32", always_2d=False)
        if getattr(wav, "ndim", 1) > 1:
            wav = wav.mean(axis=1)
        target_rate = opts.sample_rate or 44100
        return to_wav_bytes(
            np.asarray(wav, dtype=np.float32),
            source_rate=int(sr) or COSYVOICE_NATIVE_SAMPLE_RATE,
            target_rate=target_rate,
        )


async def ensure_cosyvoice_ready() -> None:
    python = resolve_cosyvoice_python()
    if python is None:
        raise EngineError("CosyVoice worker Python not configured")
    if not await ping_worker(python=python, script=_WORKER_SCRIPT, label="cosyvoice"):
        raise EngineError("CosyVoice worker ping failed")
