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

logger = logging.getLogger("voiceforge.engines.f5_tts")

F5_MODEL = "F5TTS_v1_Base"
F5_NATIVE_SAMPLE_RATE = 24000
_WHISPER_ASR_MODEL = "openai/whisper-large-v3-turbo"

# Base checkpoint is trained on English + Chinese (Emilia dataset).
SUPPORTED_LANGUAGES = ["en", "zh"]

_asr_processor = None
_asr_model = None


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

        await report("loading_model")
        await self._ensure_loaded()

        ref_source = _pick_reference_sample(sample_paths)
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_audio = out_dir / "f5_ref.wav"
        shutil.copy2(ref_source, ref_audio)

        await report("transcribing_reference")
        asr_language = _map_asr_language(language)
        device = self._resolve_device()

        def _transcribe() -> str:
            text = _transcribe_reference_audio(
                str(ref_audio),
                language=asr_language,
                device=device,
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


def _pick_reference_sample(sample_paths: list[Path]) -> Path:
    """Prefer the longest sample — more reference material helps F5-TTS."""
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


def _map_asr_language(language: str) -> str | None:
    code = (language or "en").split("-")[0].lower()
    if code in ("en", "zh"):
        return code
    # Whisper still transcribes other languages; omit hint for best effort.
    return None


def _transcribe_reference_audio(
    ref_path: str,
    *,
    language: str | None,
    device: str,
) -> str:
    """Transcribe reference audio without torchcodec (CPU Docker safe).

    F5-TTS's bundled ``model.transcribe`` and the Hugging Face ASR pipeline
    both route file/chunk loading through torchcodec, which fails on CPU-only
    images (missing ``libnvrtc.so.*``). Loading with soundfile and calling
    Whisper directly avoids that dependency.
    """
    global _asr_processor, _asr_model

    wav, sr = sf.read(ref_path, dtype="float32", always_2d=False)
    if getattr(wav, "ndim", 1) > 1:
        wav = wav.mean(axis=1)

    if sr != 16_000:
        import torch
        import torchaudio

        tensor = torchaudio.functional.resample(
            torch.from_numpy(wav).unsqueeze(0),
            sr,
            16_000,
        )
        wav = tensor.squeeze(0).numpy()
        sr = 16_000

    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    if _asr_processor is None or _asr_model is None:
        logger.info(
            "Loading Whisper ASR (%s) on device=%s for F5 reference transcription",
            _WHISPER_ASR_MODEL,
            device,
        )
        _asr_processor = WhisperProcessor.from_pretrained(_WHISPER_ASR_MODEL)
        _asr_model = WhisperForConditionalGeneration.from_pretrained(_WHISPER_ASR_MODEL)
        _asr_model.to(device)
        _asr_model.eval()

    inputs = _asr_processor(wav, sampling_rate=sr, return_tensors="pt")
    input_features = inputs.input_features.to(device)

    generate_kwargs: dict = {"max_new_tokens": 256}
    if language:
        generate_kwargs["forced_decoder_ids"] = _asr_processor.get_decoder_prompt_ids(
            language=language,
            task="transcribe",
        )

    with torch.no_grad():
        token_ids = _asr_model.generate(input_features, **generate_kwargs)

    return _asr_processor.batch_decode(token_ids, skip_special_tokens=True)[0].strip()
