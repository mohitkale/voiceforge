# Watermarking

VoiceForge can optionally mix a quiet, deterministic fingerprint into
synthesized WAV output. This is a **lightweight provenance aid**, not a
forensic watermarking system.

## Defaults

| Setting | Default | Env |
|---------|---------|-----|
| Enabled | **false** (off) | `VOICEFORGE_WATERMARK_ENABLED` |
| Strength | `0.004` (amplitude scale 0–1) | `VOICEFORGE_WATERMARK_STRENGTH` |

## What it does

Implementation: `app/watermark.py` → applied in `app/api/synth.py` after the
engine returns WAV bytes.

1. Decode the 16-bit PCM WAV to float samples.
2. Seed a PRNG from `sha256(voice_id)` (first 16 hex digits).
3. Generate unit-peak Gaussian noise matching the sample length.
4. Mix: `clip(audio + strength * noise)`.
5. Re-encode as 16-bit PCM WAV.

Same `voice_id` + strength → identical mark. Different voices → different marks.

## Audibility

At the default strength (`0.004`), the mark is intended to be **very quiet** —
typically inaudible in casual listening. Higher strengths increase detectability
and risk of audible hiss. There is no automatic loudness compensation.

## What it is for

- A weak, voice-specific fingerprint you can correlate if you keep original
  unmarked references and control your pipeline.
- An optional signal that *this deployment* tagged synth from a given voice id.

## What it is not

- **Not** tamper-proof or “forensic proof”
- **Not** a substitute for consent or disclosure
- **Not** guaranteed to survive MP3 conversion, resampling, trimming, loudness
  normalization, or added noise
- **Not** a public detector API (no `/v1/detect-watermark` endpoint)
- **Not** enabled by default

## Tests that exist

Unit/API tests check:

- marked bytes differ from unmarked
- WAV header preserved
- same voice id → deterministic output
- different voice id → different mark
- synth path applies watermark only when enabled

They do **not** prove robustness under recompression or adversarial removal.

## False positives / negatives

| Risk | Notes |
|------|-------|
| False positive | Unrelated noise can resemble a weak mark; no calibrated detector ships here |
| False negative | Re-encoding, editing, or low strength can destroy correlation |

Treat watermarking as **best-effort**, optional, and evidence-limited.
