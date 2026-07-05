"""Shared WAV export helpers for cloning engines."""

from __future__ import annotations

import io

import numpy as np


def to_wav_bytes(wav: np.ndarray, source_rate: int, target_rate: int) -> bytes:
    import soundfile as sf

    if target_rate != source_rate:
        wav = resample(wav, source_rate, target_rate)

    buf = io.BytesIO()
    sf.write(buf, wav, samplerate=target_rate, subtype="PCM_16", format="WAV")
    return buf.getvalue()


def resample(wav: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    import torch
    import torchaudio

    tensor = torch.from_numpy(wav).unsqueeze(0)
    resampled = torchaudio.functional.resample(tensor, source_rate, target_rate)
    return resampled.squeeze(0).numpy()
