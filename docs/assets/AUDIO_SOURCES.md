# Demo audio & visual sources

## Studio screenshot

| File | Source |
|------|--------|
| `docs/assets/voiceforge-studio.png` | Captured from a running VoiceForge Studio at `http://127.0.0.1:8089/` (local uvicorn). Resized for README. |

The capture may show local voice metadata from a maintainer machine. Recapture with empty `data/voices` for a cleaner public preview if desired (see [DEMO_CAPTURE.md](DEMO_CAPTURE.md)).

## Clone-flow GIF

| File | Status |
|------|--------|
| `docs/assets/clone-flow.gif` | **Not captured yet** — follow DEMO_CAPTURE.md (screen recording). README links the existing SVG flow diagram until then. |

## Engine comparison graphic

| File | Status |
|------|--------|
| `docs/assets/engine-comparison.svg` | Illustrative diagram of multi-engine → one API (not a quality ranking). |

## Audio samples

| File | Status |
|------|--------|
| `docs/assets/audio/*` | **Not generated in this pass.** Local uvicorn had `0/9` engines ready (ML stacks not installed in the lightweight `.venv`). Fabricating MP3s is prohibited. |

To generate verified samples (Docker CPU, models downloaded):

```bash
make start-cpu
# wait for health; pre-download if needed
python scripts/e2e_smoke_test.py --engine openvoice-v2 \
  --reference-wav scripts/fixtures/f5_reference_en.wav \
  --text "The birch canoe slid on the smooth planks." \
  --output-wav docs/assets/audio/openvoice-v2-demo.wav
```

Repeat for `f5-tts` and `xtts-v2` when ready. Skip engines that fail and document why.

### Reference voice for demos

Prefer `scripts/fixtures/f5_reference_en.wav` — synthetic speech, not a real person (NOTICE.md).
