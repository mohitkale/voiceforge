"""Reference-audio cleanup applied on upload before cloning.

Input quality strongly affects zero-shot clone output. This module trims
leading/trailing silence, removes very quiet gaps, applies a gentle high-pass
to cut rumble, and peak-normalizes — all with numpy/scipy only so it runs in
the base service without the ML stack installed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import soundfile as sf
from scipy import signal

# XTTS conditions on audio resampled internally at 22.05 kHz; storing samples
# at this rate keeps conditioning consistent regardless of upload format.
TARGET_SAMPLE_RATE = 22050
PEAK_DBFS = -1.0
TRIM_TOP_DB = 30.0
HIGHPASS_HZ = 80.0


@dataclass(frozen=True)
class PreprocessResult:
    samples: np.ndarray
    sample_rate: int
    duration_seconds: float
    trimmed_seconds: float


def preprocess_reference_audio(path: str) -> PreprocessResult:
    """Load, clean, and normalize a reference clip; overwrite *path* in place."""
    samples, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    mono = samples.mean(axis=1)
    original_duration = len(mono) / sample_rate if sample_rate else 0.0

    if sample_rate != TARGET_SAMPLE_RATE and sample_rate > 0:
        mono = _resample(mono, sample_rate, TARGET_SAMPLE_RATE)
        sample_rate = TARGET_SAMPLE_RATE

    mono = _highpass(mono, sample_rate)
    mono, trimmed = _trim_silence(mono, sample_rate)
    mono = _peak_normalize(mono)

    sf.write(path, mono, sample_rate, subtype="PCM_16", format="WAV")
    duration = len(mono) / sample_rate
    return PreprocessResult(
        samples=mono,
        sample_rate=sample_rate,
        duration_seconds=duration,
        trimmed_seconds=max(0.0, original_duration - duration),
    )


def _resample(wav: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or len(wav) == 0:
        return wav
    n = max(1, int(round(len(wav) * target_rate / source_rate)))
    return signal.resample(wav, n).astype(np.float32)


def _highpass(wav: np.ndarray, sample_rate: int) -> np.ndarray:
    if len(wav) < 8 or sample_rate <= 0:
        return wav
    sos = signal.butter(2, HIGHPASS_HZ, btype="highpass", fs=sample_rate, output="sos")
    return signal.sosfiltfilt(sos, wav).astype(np.float32)


def _trim_silence(wav: np.ndarray, sample_rate: int) -> tuple[np.ndarray, float]:
    """Trim leading/trailing silence using an energy threshold (librosa-style)."""
    if len(wav) == 0 or sample_rate <= 0:
        return wav, 0.0

    frame = max(1, int(0.025 * sample_rate))
    hop = max(1, frame // 4)
    ref = np.max(np.abs(wav)) or 1.0
    threshold = ref * (10 ** (-TRIM_TOP_DB / 20))

    starts: list[int] = []
    for i in range(0, len(wav) - frame + 1, hop):
        if np.max(np.abs(wav[i : i + frame])) >= threshold:
            starts.append(i)

    if not starts:
        return wav, 0.0

    start = starts[0]
    end = starts[-1] + frame
    trimmed = wav[start:end]
    removed = (len(wav) - len(trimmed)) / sample_rate
    return trimmed.astype(np.float32), removed


def _peak_normalize(wav: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(wav))) if len(wav) else 0.0
    if peak <= 1e-8:
        return wav
    target = 10 ** (PEAK_DBFS / 20)
    return (wav * (target / peak)).astype(np.float32)
