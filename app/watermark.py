"""Optional imperceptible audio watermark for synthesized output (M7).

Embeds a deterministic, voice-specific noise fingerprint at very low amplitude
so outputs can be traced without audibly degrading speech quality.
"""

from __future__ import annotations

import hashlib
import io

import numpy as np


def apply_watermark_to_wav(
    wav_bytes: bytes,
    *,
    voice_id: str,
    strength: float = 0.004,
) -> bytes:
    """Mix a quiet deterministic fingerprint into 16-bit PCM WAV bytes."""
    import soundfile as sf

    wav, sample_rate = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=False)
    if getattr(wav, "ndim", 1) > 1:
        wav = wav.mean(axis=1)

    seed = int(hashlib.sha256(voice_id.encode()).hexdigest()[:16], 16)
    rng = np.random.default_rng(seed)
    mark = rng.standard_normal(len(wav)).astype(np.float32)
    peak = float(np.max(np.abs(mark))) or 1.0
    mark = mark / peak

    mixed = np.clip(wav + strength * mark, -1.0, 1.0).astype(np.float32)

    out = io.BytesIO()
    sf.write(out, mixed, sample_rate, subtype="PCM_16", format="WAV")
    return out.getvalue()
