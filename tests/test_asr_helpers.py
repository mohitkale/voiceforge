"""Unit tests for shared ASR / sample helpers (no Whisper download)."""

from pathlib import Path

import numpy as np
import soundfile as sf

from app.engines.asr import map_asr_language, pick_longest_sample


def test_pick_longest_sample(tmp_path: Path):
    short = tmp_path / "short.wav"
    long = tmp_path / "long.wav"
    sr = 16000
    sf.write(short, np.zeros(sr, dtype=np.float32), sr)
    sf.write(long, np.zeros(sr * 3, dtype=np.float32), sr)
    assert pick_longest_sample([short, long]) == long
    assert pick_longest_sample([long, short]) == long


def test_map_asr_language():
    assert map_asr_language("en-US", {"en", "zh"}) == "en"
    assert map_asr_language("fr", {"en", "zh"}) is None
    assert map_asr_language("ja") == "ja"
