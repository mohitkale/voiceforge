"""RVC engine — high-fidelity fine-tuned voice cloning (M4).

Training and voice conversion run in an isolated RVC worker venv (see
``scripts/rvc_worker.py``) because RVC's fairseq/numpy pins conflict with
coqui-tts in the main app. Synthesis is a two-step pipeline:

  1. YourTTS generates neutral base speech (main venv / coqui-tts).
  2. RVC worker converts timbre using the per-voice trained checkpoint.

``instant`` tier is not supported — use ``high_fidelity`` for RVC training.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from app.config import get_settings
from app.engines.base import (
    CloneCapabilities,
    EngineError,
    ProgressFn,
    SynthesizeOptions,
    Tier,
    VoiceArtifact,
)
from app.engines.rvc_worker_client import (
    ensure_worker_ready,
    infer_file,
    ping_worker,
    rvc_worker_configured,
    train_model,
)
from app.engines.wav_output import to_wav_bytes
from app.storage import artifacts_dir

logger = logging.getLogger("voiceforge.engines.rvc")

YOUR_TTS_MODEL = "tts_models/multilingual/multi-dataset/your_tts"
YOUR_TTS_LANG = {
    "en": "en",
    "es": "es",
    "fr": "fr",
    "zh": "zh-cn",
    "ja": "ja",
    "ko": "en",
}
SUPPORTED_LANGUAGES = ["en", "es", "fr", "zh", "ja", "ko"]


class RvcEngine:
    id = "rvc"
    label = "RVC (Retrieval-based Voice Conversion)"
    capabilities = CloneCapabilities(
        zero_shot=False,
        fine_tunable=True,
        min_sample_seconds=180.0,
        recommended_sample_seconds=300.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=True,
        license="MIT (RVC model architecture — see RVC-Project)",
        approx_vram_gb=6.0,
    )

    def __init__(self) -> None:
        self._base_tts = None
        self._load_lock: asyncio.Lock | None = None

    def _lock(self) -> asyncio.Lock:
        if self._load_lock is None:
            self._load_lock = asyncio.Lock()
        return self._load_lock

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
        if not rvc_worker_configured():
            return False
        try:
            import TTS  # noqa: F401 — base TTS for synthesis lives in main venv
        except Exception:
            return False
        return True

    async def _check_worker(self) -> None:
        if not await ping_worker():
            await ensure_worker_ready()

    async def _ensure_base_tts(self):
        if self._base_tts is not None:
            return self._base_tts
        async with self._lock():
            if self._base_tts is not None:
                return self._base_tts

            settings = get_settings()
            settings.models_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("TTS_HOME", str(settings.models_dir))
            os.environ.setdefault("COQUI_TOS_AGREED", "1")

            def _load():
                from TTS.api import TTS

                device = self._resolve_device()
                logger.info(
                    "Loading YourTTS base for RVC synthesis on device=%s",
                    device,
                )
                return TTS(YOUR_TTS_MODEL).to(device)

            loop = asyncio.get_running_loop()
            self._base_tts = await loop.run_in_executor(None, _load)
            return self._base_tts

    async def create_voice(
        self,
        voice_id: str,
        sample_paths: list[Path],
        tier: Tier,
        language: str,
        on_progress: ProgressFn | None = None,
    ) -> VoiceArtifact:
        if tier != "high_fidelity":
            raise EngineError(
                "RVC requires tier='high_fidelity' — instant zero-shot is not "
                "supported; use xtts-v2, f5-tts, or openvoice-v2 instead"
            )
        if not sample_paths:
            raise EngineError("At least one reference sample is required")

        total_seconds = _total_duration(sample_paths)
        if total_seconds < self.capabilities.min_sample_seconds:
            raise EngineError(
                f"RVC training needs at least {self.capabilities.min_sample_seconds:.0f}s "
                f"of audio (got {total_seconds:.1f}s)"
            )

        async def report(msg: str, extra: dict | None = None) -> None:
            if on_progress:
                await on_progress(msg, extra)

        await report("checking_rvc_worker")
        await ensure_worker_ready()

        settings = get_settings()
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        work_dir = out_dir / "rvc_work"
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

        await report("training_rvc_model")
        device = self._resolve_device()
        await train_model(
            work_dir=work_dir,
            model_name=voice_id,
            sample_paths=sample_paths,
            epochs=settings.rvc_epochs,
            batch_size=settings.rvc_batch_size,
            device=device,
            on_progress=on_progress,
        )

        model_path, index_path = _locate_trained_artifacts(work_dir, voice_id)
        if model_path is None:
            raise EngineError("RVC training finished but no model weights were found")

        stored_model = out_dir / model_path.name
        stored_index = out_dir / index_path.name if index_path else None
        shutil.copy2(model_path, stored_model)
        if index_path and index_path.is_file() and stored_index:
            shutil.copy2(index_path, stored_index)

        await report("done")
        data: dict = {
            "model_path": str(stored_model.relative_to(settings.data_dir)),
            "language": _normalize_language(language),
            "version": "v2",
        }
        if stored_index and stored_index.is_file():
            data["index_path"] = str(stored_index.relative_to(settings.data_dir))

        return VoiceArtifact(engine_id=self.id, tier=tier, data=data)

    async def synthesize(
        self,
        voice_id: str,
        artifact: VoiceArtifact,
        text: str,
        opts: SynthesizeOptions,
    ) -> bytes:
        model_rel = artifact.data.get("model_path")
        if not model_rel:
            raise EngineError("Voice is missing RVC model metadata")

        settings = get_settings()
        model_path = settings.data_dir / model_rel
        if not model_path.is_file():
            raise EngineError("RVC model weights are missing on disk")

        index_rel = artifact.data.get("index_path")
        index_path = settings.data_dir / index_rel if index_rel else None

        language = _normalize_language(opts.language or artifact.data.get("language") or "en")
        if language not in SUPPORTED_LANGUAGES:
            raise EngineError(
                f"Language '{language}' is not supported by RVC "
                f"(supported: {', '.join(SUPPORTED_LANGUAGES)})"
            )

        await ensure_worker_ready()
        base_tts = await self._ensure_base_tts()
        target_rate = opts.sample_rate or 44100
        version = artifact.data.get("version") or "v2"
        device = self._resolve_device()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            base_wav = tmp_dir / "base.wav"
            out_wav = tmp_dir / "rvc_out.wav"

            def _synth_base() -> None:
                _synthesize_your_tts(base_tts, text=text, language=language, out_path=str(base_wav))

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _synth_base)

            await infer_file(
                model_path=model_path,
                index_path=index_path,
                input_path=base_wav,
                output_path=out_wav,
                device=device,
                version=version,
            )

            wav, sr = sf.read(str(out_wav), dtype="float32", always_2d=False)
            if getattr(wav, "ndim", 1) > 1:
                wav = wav.mean(axis=1)
            wav = np.asarray(wav, dtype=np.float32)

        return to_wav_bytes(wav, source_rate=sr, target_rate=target_rate)


def _normalize_language(language: str) -> str:
    code = (language or "en").split("-")[0].lower()
    if code == "zh":
        return "zh"
    return code


def _total_duration(sample_paths: list[Path]) -> float:
    total = 0.0
    for path in sample_paths:
        try:
            info = sf.info(str(path))
            total += info.frames / info.samplerate if info.samplerate else 0.0
        except Exception:  # noqa: BLE001, S112 — skip unreadable samples
            continue
    return total


def _locate_trained_artifacts(work_dir: Path, model_name: str) -> tuple[Path | None, Path | None]:
    """Find best .pth and optional .index after rvc-no-gui training."""
    candidates: list[Path] = []
    for pattern in ("**/*.pth", "**/*.pt"):
        candidates.extend(work_dir.rglob(pattern))

    if not candidates:
        models_dir = work_dir / "rvc_models" / model_name
        if models_dir.is_dir():
            candidates.extend(models_dir.rglob("*.pth"))

    if not candidates:
        return None, None

    # Prefer latest modified generator checkpoint (G_*.pth).
    pth_files = sorted(
        [p for p in candidates if p.suffix in {".pth", ".pt"} and p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    model_path = pth_files[0] if pth_files else None

    index_files = sorted(
        work_dir.rglob("*.index"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    index_path = index_files[0] if index_files else None
    return model_path, index_path


def _synthesize_your_tts(base_tts, *, text: str, language: str, out_path: str) -> None:
    lang = _normalize_language(language)
    your_tts_lang = YOUR_TTS_LANG.get(lang)
    if your_tts_lang is None:
        raise EngineError(f"No YourTTS mapping for language '{lang}'")
    speakers = base_tts.speakers
    if not speakers:
        raise EngineError("YourTTS returned no speakers")
    base_tts.tts_to_file(
        text=text,
        speaker=speakers[0],
        language=your_tts_lang,
        file_path=out_path,
    )
