import io

import numpy as np
import soundfile as sf

from app.watermark import apply_watermark_to_wav


def test_watermark_changes_audio_but_preserves_shape():
    sr = 22050
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    wav = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, wav, sr, subtype="PCM_16", format="WAV")
    original = buf.getvalue()

    marked = apply_watermark_to_wav(original, voice_id="voice-a", strength=0.01)
    assert marked != original
    assert marked[:4] == b"RIFF"

    again = apply_watermark_to_wav(original, voice_id="voice-a", strength=0.01)
    assert marked == again

    other = apply_watermark_to_wav(original, voice_id="voice-b", strength=0.01)
    assert other != marked


def test_watermark_deterministic_per_voice():
    sr = 16000
    wav = np.zeros(sr, dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, wav, sr, subtype="PCM_16", format="WAV")
    raw = buf.getvalue()

    a1 = apply_watermark_to_wav(raw, voice_id="same", strength=0.005)
    a2 = apply_watermark_to_wav(raw, voice_id="same", strength=0.005)
    assert a1 == a2
