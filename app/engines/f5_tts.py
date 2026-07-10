"""F5-TTS engine — zero-shot cloning via the SWivid diffusion-transformer model.

Apache-2.0 / CC licensed weights (permissive vs XTTS-v2's CPML). Requires a
transcript of the reference audio (`ref_text`); VoiceForge auto-transcribes
the uploaded sample at voice-creation time and caches it in the artifact.

Heavy imports are deferred to first use, matching the XTTS-v2 engine pattern.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.engines.asr import (
    map_asr_language,
    pick_longest_sample,
    release_asr_model,
    transcribe_reference_audio,
)
from app.engines.base import (
    CloneCapabilities,
    EngineError,
    ProgressFn,
    SynthesizeOptions,
    Tier,
    VoiceArtifact,
)
from app.engines.wav_output import to_wav_bytes
from app.storage import artifacts_dir

logger = logging.getLogger("voiceforge.engines.f5_tts")

F5_MODEL = "F5TTS_v1_Base"
F5_NATIVE_SAMPLE_RATE = 24000

# Base checkpoint is trained on English + Chinese (Emilia dataset).
SUPPORTED_LANGUAGES = ["en", "zh"]


class F5TtsEngine:
    id = "f5-tts"
    label = "F5-TTS v1 (SWivid)"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=6.0,
        recommended_sample_seconds=12.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=False,
        license="Apache-2.0 / CC (model weights) — see SWivid/F5-TTS repo",
        approx_vram_gb=4.0,
    )

    def __init__(self) -> None:
        self._model = None
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
        if self._model is not None:
            return True
        try:
            import f5_tts  # noqa: F401
        except Exception:
            return False
        return True

    async def _ensure_loaded(self):
        if self._model is not None:
            return self._model
        async with self._lock():
            if self._model is not None:
                return self._model

            settings = get_settings()
            settings.models_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("HF_HOME", str(settings.models_dir))

            def _load():
                try:
                    from f5_tts.api import F5TTS
                except Exception as exc:  # pragma: no cover
                    raise EngineError(
                        "F5-TTS dependencies are not installed. Install the "
                        "'f5' extra or use the Docker image."
                    ) from exc
                device = self._resolve_device()
                logger.info(
                    "Loading F5-TTS (%s) on device=%s (first run may download checkpoints)",
                    F5_MODEL,
                    device,
                )
                return F5TTS(
                    model=F5_MODEL,
                    device=device,
                    hf_cache_dir=str(settings.models_dir),
                )

            loop = asyncio.get_running_loop()
            self._model = await loop.run_in_executor(None, _load)
            return self._model

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

        async def report(msg: str, extra: dict | None = None) -> None:
            if on_progress:
                await on_progress(msg, extra)

        await report("caching_reference")
        ref_source = pick_longest_sample(sample_paths)
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_audio = out_dir / "f5_ref.wav"
        shutil.copy2(ref_source, ref_audio)

        await report("transcribing_reference")
        asr_language = map_asr_language(language, {"en", "zh"})

        def _transcribe() -> str:
            # CPU ASR avoids T4 VRAM contention with F5-TTS on CUDA.
            text = transcribe_reference_audio(
                str(ref_audio),
                language=asr_language,
                device="cpu",
            )
            if not (text or "").strip():
                raise EngineError(
                    "Could not transcribe the reference audio — F5-TTS needs "
                    "ref_text; try a clearer clip with intelligible speech"
                )
            return text.strip()

        loop = asyncio.get_running_loop()
        try:
            ref_text = await loop.run_in_executor(None, _transcribe)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Reference transcription failed: {exc}") from exc
        finally:
            release_asr_model()

        await report("loading_model")
        await self._ensure_loaded()

        await report("done")
        settings = get_settings()
        return VoiceArtifact(
            engine_id=self.id,
            tier=tier,
            data={
                "ref_audio_path": str(ref_audio.relative_to(settings.data_dir)),
                "ref_text": ref_text,
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
        ref_rel = artifact.data.get("ref_audio_path")
        ref_text = artifact.data.get("ref_text")
        if not ref_rel or not ref_text:
            raise EngineError("Voice is missing F5-TTS reference audio or transcript")

        ref_path = get_settings().data_dir / ref_rel
        if not ref_path.exists():
            raise EngineError("Cached reference audio is missing on disk")

        model = await self._ensure_loaded()
        target_rate = opts.sample_rate or 44100
        speed = opts.speed or 1.0

        def _synth() -> np.ndarray:
            import tqdm

            wav, _sr, _spec = model.infer(
                ref_file=str(ref_path),
                ref_text=ref_text,
                gen_text=text,
                speed=speed,
                show_info=lambda *_args, **_kwargs: None,
                progress=tqdm,
            )
            if wav is None:
                raise EngineError("F5-TTS produced no audio")
            return np.asarray(wav, dtype=np.float32)

        loop = asyncio.get_running_loop()
        try:
            wav = await loop.run_in_executor(None, _synth)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Synthesis failed: {exc}") from exc

        return to_wav_bytes(wav, source_rate=F5_NATIVE_SAMPLE_RATE, target_rate=target_rate)
