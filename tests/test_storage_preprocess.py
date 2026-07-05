import io

import numpy as np
import soundfile as sf

from app.storage import save_and_validate_sample


def _silent_wav(seconds: float = 3.0, rate: int = 22050) -> bytes:
    samples = np.zeros(int(seconds * rate), dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, samples, rate, subtype="PCM_16", format="WAV")
    return buf.getvalue()


def _tone_wav(seconds: float = 3.0, rate: int = 22050) -> bytes:
    t = np.arange(int(seconds * rate), dtype=np.float32) / rate
    samples = (0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, samples, rate, subtype="PCM_16", format="WAV")
    return buf.getvalue()


def test_upload_preprocesses_to_target_rate(tmp_path, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "preprocess_samples", True)

    voice_id = "v-pre"
    ingested = save_and_validate_sample(voice_id, _tone_wav(rate=44100), "ref.wav")
    assert ingested.sample_rate == 22050

    data, rate = sf.read(ingested.path, dtype="float32")
    assert rate == 22050
    assert np.max(np.abs(data)) > 0.01
