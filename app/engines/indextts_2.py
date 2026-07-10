"""IndexTTS2 engine — zero-shot cloning via an isolated worker venv.

Main app stays on Python 3.11 / coqui pins; IndexTTS runs under
``VOICEFORGE_INDEXTTS_PYTHON`` (default ``/opt/indextts-venv/bin/python``).
"""

from __future__ import annotations

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
from app.engines.wav_output import to_wav_bytes
from app.engines.worker_client import ping_worker, run_worker
from app.storage import artifacts_dir

_WORKER_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "indextts_worker.py"
INDEXTTS_NATIVE_SAMPLE_RATE = 22050

SUPPORTED_LANGUAGES = ["en", "zh"]


def resolve_indextts_python() -> Path | None:
    settings = get_settings()
    if settings.indextts_python:
        path = Path(settings.indextts_python)
        return path if path.is_file() else None
    default = Path("/opt/indextts-venv/bin/python")
    if default.is_file():
        return default
    return None


def indextts_worker_configured() -> bool:
    return resolve_indextts_python() is not None and _WORKER_SCRIPT.is_file()


class IndexTts2Engine:
    id = "indextts-2"
    label = "IndexTTS2 (Bilibili IndexTeam)"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=3.0,
        recommended_sample_seconds=8.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=True,
        license="Check IndexTTS / IndexTeam upstream license before commercial use",
        approx_vram_gb=8.0,
    )

    def is_ready(self) -> bool:
        return indextts_worker_configured()

    def _model_dir(self) -> Path:
        return get_settings().models_dir / "IndexTTS-2"

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
        if not indextts_worker_configured():
            raise EngineError(
                "IndexTTS worker is not configured — set VOICEFORGE_INDEXTTS_PYTHON "
                "to an interpreter with IndexTTS2 installed"
            )

        async def report(msg: str, extra: dict | None = None) -> None:
            if on_progress:
                await on_progress(msg, extra)

        await report("caching_reference")
        ref_source = pick_longest_sample(sample_paths)
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_audio = out_dir / "indextts_ref.wav"
        shutil.copy2(ref_source, ref_audio)

        model_dir = self._model_dir()
        if not model_dir.exists():
            await report("downloading_model")
            python = resolve_indextts_python()
            assert python is not None
            await run_worker(
                python=python,
                script=_WORKER_SCRIPT,
                args=["setup", "--models-dir", str(get_settings().models_dir)],
                label="indextts",
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
        python = resolve_indextts_python()
        if python is None:
            raise EngineError("VOICEFORGE_INDEXTTS_PYTHON is not configured")

        ref_rel = artifact.data.get("ref_audio_path")
        if not ref_rel:
            raise EngineError("Voice is missing IndexTTS reference audio")

        ref_path = get_settings().data_dir / ref_rel
        if not ref_path.exists():
            raise EngineError("Cached reference audio is missing on disk")

        model_dir = Path(artifact.data.get("model_dir") or self._model_dir())
        out_wav = artifacts_dir(voice_id) / "indextts_last.wav"

        await run_worker(
            python=python,
            script=_WORKER_SCRIPT,
            args=[
                "synthesize",
                "--model-dir",
                str(model_dir),
                "--ref-audio",
                str(ref_path),
                "--text",
                text,
                "--output",
                str(out_wav),
            ],
            label="indextts",
            timeout_s=1800.0,
        )

        if not out_wav.is_file():
            raise EngineError("IndexTTS worker did not produce output audio")

        wav, sr = sf.read(str(out_wav), dtype="float32", always_2d=False)
        if getattr(wav, "ndim", 1) > 1:
            wav = wav.mean(axis=1)
        target_rate = opts.sample_rate or 44100
        return to_wav_bytes(
            np.asarray(wav, dtype=np.float32),
            source_rate=int(sr) or INDEXTTS_NATIVE_SAMPLE_RATE,
            target_rate=target_rate,
        )


async def ensure_indextts_ready() -> None:
    python = resolve_indextts_python()
    if python is None:
        raise EngineError("IndexTTS worker Python not configured")
    if not await ping_worker(python=python, script=_WORKER_SCRIPT, label="indextts"):
        raise EngineError("IndexTTS worker ping failed")
