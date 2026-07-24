"""Shared Whisper ASR for engines that need a reference transcript (ref_text).

Loads audio with soundfile (CPU-Docker safe — avoids torchcodec) and calls
Whisper directly. Used by F5-TTS, Qwen3-TTS, Fish Speech, CosyVoice, etc.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger("voiceforge.engines.asr")

WHISPER_ASR_MODEL = "openai/whisper-large-v3-turbo"

_asr_processor = None
_asr_model = None


def pick_longest_sample(sample_paths: list[Path]) -> Path:
    """Prefer the longest sample — more reference material helps cloning."""
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


def map_asr_language(language: str, supported: set[str] | None = None) -> str | None:
    code = (language or "en").split("-")[0].lower()
    if supported is None:
        return code if code else None
    if code in supported:
        return code
    return None


def transcribe_reference_audio(
    ref_path: str | Path,
    *,
    language: str | None,
    device: str,
) -> str:
    """Transcribe reference audio without torchcodec (CPU Docker safe)."""
    global _asr_processor, _asr_model

    from app.config import get_settings

    provider_id = get_settings().reference_asr_provider
    if provider_id == "qwen3-asr":
        from app.audio_intelligence.qwen3_asr import Qwen3AsrProvider

        result = Qwen3AsrProvider().transcribe(
            Path(ref_path),
            language=language,
            timestamps=False,
        )
        return result.text
    if provider_id != "whisper":
        raise ValueError(
            f"Unsupported reference ASR provider '{provider_id}'; expected whisper or qwen3-asr"
        )

    wav, sr = sf.read(str(ref_path), dtype="float32", always_2d=False)
    if getattr(wav, "ndim", 1) > 1:
        wav = wav.mean(axis=1)

    if sr != 16_000:
        import torch
        import torchaudio

        tensor = torchaudio.functional.resample(
            torch.from_numpy(np.asarray(wav, dtype=np.float32)).unsqueeze(0),
            sr,
            16_000,
        )
        wav = tensor.squeeze(0).numpy()
        sr = 16_000

    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    if _asr_processor is None or _asr_model is None:
        logger.info(
            "Loading Whisper ASR (%s) on device=%s for reference transcription",
            WHISPER_ASR_MODEL,
            device,
        )
        _asr_processor = WhisperProcessor.from_pretrained(WHISPER_ASR_MODEL)
        _asr_model = WhisperForConditionalGeneration.from_pretrained(WHISPER_ASR_MODEL)
        _asr_model.to(device)
        _asr_model.eval()

    inputs = _asr_processor(wav, sampling_rate=sr, return_tensors="pt")
    input_features = inputs.input_features.to(device)

    generate_kwargs: dict = {
        # Whisper encoder/decoder limit is 448 tokens; leave headroom for
        # forced language/task prompt tokens (decoder_input_ids).
        "max_new_tokens": 224,
    }
    if language:
        generate_kwargs["forced_decoder_ids"] = _asr_processor.get_decoder_prompt_ids(
            language=language,
            task="transcribe",
        )

    with torch.no_grad():
        token_ids = _asr_model.generate(input_features, **generate_kwargs)

    return _asr_processor.batch_decode(token_ids, skip_special_tokens=True)[0].strip()


def release_asr_model() -> None:
    """Drop cached Whisper weights to free GPU memory for TTS models."""
    global _asr_processor, _asr_model
    if _asr_model is not None:
        try:
            import torch

            _asr_model.to("cpu")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            # Best-effort cleanup — free references even if CUDA teardown fails.
            logger.debug("ASR CUDA cleanup failed", exc_info=True)
    _asr_processor = None
    _asr_model = None
