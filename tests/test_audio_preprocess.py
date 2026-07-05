import numpy as np
import pytest
import soundfile as sf

from app.audio_preprocess import (
    PEAK_DBFS,
    TARGET_SAMPLE_RATE,
    _peak_normalize,
    _trim_silence,
    preprocess_reference_audio,
)


def _write_wav(path, samples: np.ndarray, rate: int = TARGET_SAMPLE_RATE) -> None:
    sf.write(path, samples, rate, subtype="PCM_16")


def test_trim_silence_removes_quiet_edges(tmp_path):
    rate = TARGET_SAMPLE_RATE
    speech = np.sin(2 * np.pi * 440 * np.arange(rate) / rate).astype(np.float32) * 0.5
    silence = np.zeros(rate, dtype=np.float32)
    wav = np.concatenate([silence, speech, silence])
    trimmed, removed = _trim_silence(wav, rate)
    assert len(trimmed) < len(wav)
    assert removed > 1.0
    assert np.max(np.abs(trimmed)) > 0.1


def test_peak_normalize_targets_dbfs():
    wav = np.array([0.25, -0.5, 0.1], dtype=np.float32)
    out = _peak_normalize(wav)
    target = 10 ** (PEAK_DBFS / 20)
    assert pytest.approx(float(np.max(np.abs(out))), rel=1e-4) == target


def test_preprocess_overwrites_file_and_resamples(tmp_path):
    rate = 44100
    t = np.arange(rate * 2, dtype=np.float32) / rate
    samples = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    path = tmp_path / "sample.wav"
    _write_wav(path, samples, rate)

    result = preprocess_reference_audio(str(path))
    assert result.sample_rate == TARGET_SAMPLE_RATE
    assert result.duration_seconds > 0

    reread, reread_rate = sf.read(path, dtype="float32")
    assert reread_rate == TARGET_SAMPLE_RATE
    assert len(reread) == int(result.duration_seconds * TARGET_SAMPLE_RATE)


def test_preprocess_rejects_empty_after_trim(tmp_path):
    path = tmp_path / "silent.wav"
    _write_wav(path, np.zeros(TARGET_SAMPLE_RATE * 2, dtype=np.float32))
    # Should still write something (trim keeps silence if no speech detected)
    result = preprocess_reference_audio(str(path))
    assert result.duration_seconds > 0
