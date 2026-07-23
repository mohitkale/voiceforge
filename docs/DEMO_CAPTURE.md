# Demo capture process

How to reproduce README visuals and audio **without** celebrity voices, private
samples, or fabricated engine output.

## Rules

1. Use only **your own** voice (document permission) **or** the synthetic fixture
   `scripts/fixtures/f5_reference_en.wav` (NOTICE: not a real person).
2. Never commit API tokens, `.env`, or `data/voices/` with personal audio.
3. Demo audio must be produced by a running VoiceForge instance — do not invent
   MP3/WAV files that the engines did not generate.
4. If an engine cannot run (GPU/memory/weights), **omit** its sample and note why.

## Neutral demo sentence

Use the same text for every engine comparison:

> The birch canoe slid on the smooth planks.

## Capture Studio screenshot

1. `make start-cpu` (or local uvicorn for UI-only layout checks).
2. Open http://localhost:8089/
3. Select `openvoice-v2`, show upload/record area, consent checked, text box,
   and (if available) a generated player — **without** personal names in fields.
4. Save as `docs/assets/voiceforge-studio.png` (reasonable width, &lt;1.5 MB).

## Capture clone-flow GIF

Record a short screen capture (Kap, OBS, or `ffmpeg` desktop capture) showing:

1. Choose OpenVoice  
2. Upload the synthetic fixture or your consented sample  
3. Confirm consent  
4. Start cloning  
5. Enter the neutral sentence  
6. Generate and play  

Export `docs/assets/clone-flow.gif` under ~5–8 MB if possible.

## Capture engine comparison audio

With the service healthy and models downloaded:

```bash
REF=scripts/fixtures/f5_reference_en.wav
TEXT='The birch canoe slid on the smooth planks.'
OUT=docs/assets/audio

for ENGINE in openvoice-v2 f5-tts xtts-v2; do
  python scripts/e2e_smoke_test.py --engine "$ENGINE" --reference-wav "$REF" \
    --text "$TEXT" --output-wav "$OUT/${ENGINE}-demo.wav" || true
done
```

Convert to MP3 only if you have `ffmpeg` and want smaller README embeds:

```bash
ffmpeg -y -i docs/assets/audio/openvoice-v2-demo.wav \
  docs/assets/audio/openvoice-v2-demo.mp3
```

### Engines often missing on a laptop CPU session

| Engine | Typical blocker |
|--------|-----------------|
| `qwen3-tts` | Memory / first download size |
| `chatterbox` | Worker/venv not ready outside Docker |
| `rvc` | GPU + long audio + high_fidelity tier |
| `fish-speech` | Sidecar not running |
| `cosyvoice-3` / `indextts-2` | Worker venv not installed; GPU preferred |

Document omissions in the README audio table (“not captured — &lt;reason&gt;”).

## Waveforms (optional)

Generate PNG waveforms from captured WAV with any tool you trust, or skip.
Store under `docs/assets/waveforms/`. Do not invent waveforms for missing audio.

## Permission note for personal voice demos

If you use your own voice, add a one-line note in the PR or
`docs/assets/AUDIO_SOURCES.md`:

```text
Demo voice: maintainer's own recording, consented for redistribution in docs/.
Source sentence: "The birch canoe slid on the smooth planks."
```

## Current repo status

See `docs/assets/AUDIO_SOURCES.md` for which files exist and how they were made.
