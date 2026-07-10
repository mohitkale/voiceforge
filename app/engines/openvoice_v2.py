"""OpenVoice V2 engine — MIT-licensed zero-shot cloning via Coqui TTS.

Uses coqui-tts's bundled OpenVoice V2 voice-conversion checkpoint (same stack
as XTTS-v2 — no extra git installs). Synthesis is a two-step pipeline:

  1. Base TTS (YourTTS or a language-specific Tacotron2) generates neutral speech.
  2. OpenVoice VC converts the tone color to match the cached reference speaker.

Heavy imports are deferred to first use, matching the other engine modules.
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
from app.engines.wav_output import to_wav_bytes
from app.storage import artifacts_dir

logger = logging.getLogger("voiceforge.engines.openvoice_v2")

OV_VC_MODEL = "voice_conversion_models/multilingual/multi-dataset/openvoice_v2"
YOUR_TTS_MODEL = "tts_models/multilingual/multi-dataset/your_tts"

# OpenVoice V2 natively supports these output languages (MyShell docs).
SUPPORTED_LANGUAGES = ["en", "es", "fr", "zh", "ja", "ko"]

# Coqui YourTTS language codes differ slightly from our API codes.
YOUR_TTS_LANG = {
    "en": "en",
    "es": "es",
    "fr": "fr",
    "zh": "zh-cn",
    "ja": "ja",
    # Korean is not in YourTTS — synthesize with English base; OpenVoice VC
    # still applies the cloned tone color cross-lingually.
    "ko": "en",
}

# OpenVoice V2 checkpoints in coqui-tts use 22.05 kHz audio.
OPENVOICE_NATIVE_SAMPLE_RATE = 22050


class OpenVoiceV2Engine:
    id = "openvoice-v2"
    label = "OpenVoice V2 (MyShell, via Coqui VC)"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=3.0,
        recommended_sample_seconds=8.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=False,
        license="MIT (OpenVoice V2 VC) + YourTTS base (verify Coqui model card)",
        approx_vram_gb=2.0,
    )

    def __init__(self) -> None:
        self._vc = None
        self._base_tts: dict[str, object] = {}
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

    def _use_gpu(self) -> bool:
        """Coqui-TTS still needs ``gpu=True`` at construction — ``.to('cuda')``
        alone leaves YourTTS speaker encoders on CPU (idiap/coqui-tts #4398)."""
        return self._resolve_device().startswith("cuda")

    def is_ready(self) -> bool:
        if self._vc is not None:
            return True
        try:
            import TTS  # noqa: F401
        except Exception:
            return False
        return True

    def _prepare_env(self) -> None:
        settings = get_settings()
        settings.models_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("TTS_HOME", str(settings.models_dir))

    async def _ensure_vc(self):
        if self._vc is not None:
            return self._vc
        async with self._lock():
            if self._vc is not None:
                return self._vc

            self._prepare_env()

            def _load():
                try:
                    from TTS.api import TTS
                except Exception as exc:  # pragma: no cover
                    raise EngineError(
                        "OpenVoice V2 dependencies are not installed. Install the "
                        "'xtts' extra (torch + coqui-tts) or use the Docker image."
                    ) from exc
                device = self._resolve_device()
                gpu = self._use_gpu()
                logger.info(
                    "Loading OpenVoice V2 VC (%s) on device=%s gpu=%s",
                    OV_VC_MODEL,
                    device,
                    gpu,
                )
                tts = TTS(OV_VC_MODEL, gpu=gpu)
                return tts.to(device) if gpu else tts

            loop = asyncio.get_running_loop()
            self._vc = await loop.run_in_executor(None, _load)
            return self._vc

    async def _ensure_base_tts(self, language: str):
        lang = _normalize_language(language)
        cached = self._base_tts.get(lang)
        if cached is not None:
            return cached

        async with self._lock():
            cached = self._base_tts.get(lang)
            if cached is not None:
                return cached

            self._prepare_env()
            model_name = YOUR_TTS_MODEL

            def _load():
                from TTS.api import TTS

                device = self._resolve_device()
                gpu = self._use_gpu()
                logger.info(
                    "Loading OpenVoice base TTS (%s) for language=%s on device=%s gpu=%s",
                    model_name,
                    lang,
                    device,
                    gpu,
                )
                tts = TTS(model_name, gpu=gpu)
                return tts.to(device) if gpu else tts

            loop = asyncio.get_running_loop()
            tts = await loop.run_in_executor(None, _load)
            self._base_tts[lang] = tts
            return tts

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

        await report("loading_model")
        vc = await self._ensure_vc()

        ref_source = _pick_reference_sample(sample_paths)
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_audio = out_dir / "openvoice_ref.wav"
        shutil.copy2(ref_source, ref_audio)
        cache_dir = out_dir / "openvoice_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        await report("caching_speaker_embedding")
        target_paths = [str(p) for p in sample_paths]

        def _warm_cache() -> None:
            # Prime the VC speaker cache so synthesis only needs `speaker=voice_id`.
            vc.voice_conversion(
                source_wav=str(ref_audio),
                target_wav=target_paths,
                speaker=voice_id,
                voice_dir=str(cache_dir),
            )

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _warm_cache)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Failed to cache OpenVoice speaker embedding: {exc}") from exc

        await report("done")
        settings = get_settings()
        return VoiceArtifact(
            engine_id=self.id,
            tier=tier,
            data={
                "ref_audio_path": str(ref_audio.relative_to(settings.data_dir)),
                "speaker_cache_id": voice_id,
                "voice_dir": str(cache_dir.relative_to(settings.data_dir)),
                "language": _normalize_language(language),
            },
        )

    async def synthesize(
        self,
        voice_id: str,
        artifact: VoiceArtifact,
        text: str,
        opts: SynthesizeOptions,
    ) -> bytes:
        speaker_id = artifact.data.get("speaker_cache_id") or voice_id
        voice_dir_rel = artifact.data.get("voice_dir")
        if not voice_dir_rel:
            raise EngineError("Voice is missing OpenVoice speaker cache metadata")

        voice_dir = get_settings().data_dir / voice_dir_rel
        if not voice_dir.exists():
            raise EngineError("OpenVoice speaker cache directory is missing on disk")

        language = _normalize_language(opts.language or artifact.data.get("language") or "en")
        if language not in SUPPORTED_LANGUAGES:
            raise EngineError(
                f"Language '{language}' is not supported by OpenVoice V2 "
                f"(supported: {', '.join(SUPPORTED_LANGUAGES)})"
            )

        vc = await self._ensure_vc()
        base_tts = await self._ensure_base_tts(language)
        target_rate = opts.sample_rate or 44100

        def _synth() -> np.ndarray:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                src_path = tmp.name
            try:
                use_gpu = self._use_gpu()
                _synthesize_base(
                    base_tts,
                    text=text,
                    language=language,
                    out_path=src_path,
                    gpu=use_gpu,
                )
                wav = vc.voice_conversion(
                    source_wav=src_path,
                    speaker=speaker_id,
                    voice_dir=str(voice_dir),
                )
            finally:
                Path(src_path).unlink(missing_ok=True)

            if wav is None or len(wav) == 0:
                raise EngineError("OpenVoice V2 produced no audio")
            return np.asarray(wav, dtype=np.float32)

        loop = asyncio.get_running_loop()
        try:
            wav = await loop.run_in_executor(None, _synth)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Synthesis failed: {exc}") from exc

        return to_wav_bytes(
            wav,
            source_rate=OPENVOICE_NATIVE_SAMPLE_RATE,
            target_rate=target_rate,
        )


def _normalize_language(language: str) -> str:
    code = (language or "en").split("-")[0].lower()
    if code == "zh":
        return "zh"
    return code


def _pick_reference_sample(sample_paths: list[Path]) -> Path:
    best = sample_paths[0]
    best_dur = 0.0
    for path in sample_paths:
        try:
            info = sf.info(str(path))
            dur = info.frames / info.samplerate if info.samplerate else 0.0
        except Exception:
            dur = 0.0
        if dur >= best_dur:
            best, best_dur = path, dur
    return best


def _synthesize_base(
    base_tts,
    *,
    text: str,
    language: str,
    out_path: str,
    gpu: bool = False,
) -> None:
    """Generate neutral base speech for OpenVoice tone-color conversion."""
    lang = _normalize_language(language)
    your_tts_lang = YOUR_TTS_LANG.get(lang)
    if your_tts_lang is None:
        raise EngineError(f"No base TTS mapping for language '{lang}'")

    speakers = base_tts.speakers
    if not speakers:
        raise EngineError("YourTTS base model returned no speakers")
    base_tts.tts_to_file(
        text=text,
        speaker=speakers[0],
        language=your_tts_lang,
        file_path=out_path,
        gpu=gpu,
    )
