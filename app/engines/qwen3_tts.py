"""Qwen3-TTS 1.7B Base — Apache-2.0 zero-shot voice cloning.

Uses ``qwen-tts`` / ``Qwen3TTSModel.generate_voice_clone``. Requires a
reference transcript (auto-transcribed via Whisper); falls back to
``x_vector_only_mode`` if ASR fails.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

import numpy as np

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
from app.providers.registry import QWEN3_TTS_REVISION
from app.runtime_device import resolve_torch_device, transformers_device_map
from app.storage import artifacts_dir

logger = logging.getLogger("voiceforge.engines.qwen3_tts")

QWEN3_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
QWEN3_MODEL_REVISION = QWEN3_TTS_REVISION
QWEN3_NATIVE_SAMPLE_RATE = 24000

SUPPORTED_LANGUAGES = [
    "en", "zh", "ja", "ko", "de", "fr", "ru", "pt", "es", "it",
]

# qwen-tts's `generate_voice_clone` expects full language names, not ISO
# 639-1 codes (e.g. "english", not "en").
_QWEN3_LANGUAGE_NAMES = {
    "en": "english",
    "zh": "chinese",
    "ja": "japanese",
    "ko": "korean",
    "de": "german",
    "fr": "french",
    "ru": "russian",
    "pt": "portuguese",
    "es": "spanish",
    "it": "italian",
}


class Qwen3TtsEngine:
    id = "qwen3-tts"
    label = "Qwen3-TTS 1.7B Voice Clone"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=3.0,
        recommended_sample_seconds=8.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=False,
        license="Apache-2.0 (Qwen3-TTS)",
        approx_vram_gb=6.0,
    )

    def __init__(self) -> None:
        self._model = None
        self._load_lock: asyncio.Lock | None = None

    def _lock(self) -> asyncio.Lock:
        if self._load_lock is None:
            self._load_lock = asyncio.Lock()
        return self._load_lock

    def _resolve_device(self) -> str:
        return resolve_torch_device(get_settings().device)

    def is_ready(self) -> bool:
        if self._model is not None:
            return True
        model_dir = get_settings().qwen3_tts_model_dir
        if model_dir is None or not model_dir.is_dir():
            return False
        try:
            import qwen_tts  # noqa: F401
        except Exception:
            try:
                from qwen_tts import Qwen3TTSModel  # noqa: F401
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
            model_dir = settings.qwen3_tts_model_dir
            if model_dir is None or not model_dir.is_dir():
                raise EngineError(
                    "Qwen3-TTS is not configured; set "
                    "VOICEFORGE_QWEN3_TTS_MODEL_DIR to an explicitly downloaded "
                    "local snapshot"
                )

            def _load():
                try:
                    import torch
                    from qwen_tts import Qwen3TTSModel
                except Exception as exc:  # pragma: no cover
                    raise EngineError(
                        "Qwen3-TTS dependencies are not installed. Install the "
                        "'qwen3' extra or use requirements-qwen3.txt."
                    ) from exc
                device = self._resolve_device()
                device_map = transformers_device_map(device)
                # Keep CPU/MPS on fp32 until upstream documents a stable lower
                # precision path. CUDA uses bfloat16 as in the official examples.
                dtype = torch.bfloat16 if device == "cuda" else torch.float32
                logger.info(
                    "Loading Qwen3-TTS (%s) on device_map=%s",
                    model_dir,
                    device_map,
                )
                return Qwen3TTSModel.from_pretrained(
                    str(model_dir),
                    device_map=device_map,
                    dtype=dtype,
                    local_files_only=True,
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
        ref_audio = out_dir / "qwen3_ref.wav"
        shutil.copy2(ref_source, ref_audio)

        await report("transcribing_reference")
        asr_language = map_asr_language(language, set(SUPPORTED_LANGUAGES))
        device = self._resolve_device()
        x_vector_only = False
        ref_text = ""

        def _transcribe() -> str:
            return transcribe_reference_audio(
                str(ref_audio),
                language=asr_language,
                device=device,
            )

        loop = asyncio.get_running_loop()
        try:
            ref_text = await loop.run_in_executor(None, _transcribe)
            if not (ref_text or "").strip():
                x_vector_only = True
                ref_text = ""
                logger.warning(
                    "Qwen3-TTS ASR empty for voice %s — using x_vector_only_mode",
                    voice_id,
                )
        except Exception as exc:
            x_vector_only = True
            ref_text = ""
            logger.warning(
                "Qwen3-TTS ASR failed for voice %s (%s) — using x_vector_only_mode",
                voice_id,
                exc,
            )

        await report("done")
        settings = get_settings()
        return VoiceArtifact(
            engine_id=self.id,
            tier=tier,
            data={
                "ref_audio_path": str(ref_audio.relative_to(settings.data_dir)),
                "ref_text": ref_text,
                "x_vector_only_mode": x_vector_only,
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
        if not ref_rel:
            raise EngineError("Voice is missing Qwen3-TTS reference audio")

        ref_path = get_settings().data_dir / ref_rel
        if not ref_path.exists():
            raise EngineError("Cached reference audio is missing on disk")

        model = await self._ensure_loaded()
        target_rate = opts.sample_rate or 44100
        language_code = opts.language or artifact.data.get("language") or "en"
        language = _QWEN3_LANGUAGE_NAMES.get(language_code, language_code)
        ref_text = artifact.data.get("ref_text") or ""
        x_vector_only = bool(artifact.data.get("x_vector_only_mode"))

        def _synth() -> tuple[np.ndarray, int]:
            kwargs: dict = {
                "text": text,
                "language": language,
                "ref_audio": str(ref_path),
            }
            if x_vector_only or not ref_text:
                kwargs["x_vector_only_mode"] = True
            else:
                kwargs["ref_text"] = ref_text

            result = model.generate_voice_clone(**kwargs)
            if isinstance(result, tuple) and len(result) >= 2:
                wavs, sr = result[0], result[1]
            else:
                wavs, sr = result, QWEN3_NATIVE_SAMPLE_RATE

            if isinstance(wavs, (list, tuple)):
                wav = wavs[0]
            else:
                wav = wavs
            if hasattr(wav, "cpu"):
                arr = wav.squeeze().detach().cpu().numpy().astype(np.float32)
            else:
                arr = np.asarray(wav, dtype=np.float32).squeeze()
            return arr, int(sr)

        loop = asyncio.get_running_loop()
        try:
            wav, source_rate = await loop.run_in_executor(None, _synth)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Synthesis failed: {exc}") from exc

        return to_wav_bytes(wav, source_rate=source_rate, target_rate=target_rate)
