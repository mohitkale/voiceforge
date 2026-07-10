# Third-party notices

This file clarifies what the **MIT license on this repository covers**, and
what it does **not**. VoiceForge downloads and runs third-party ML models at
runtime; those weights and some optional training tools have their own terms.

## This repository (service code)

| Component | License |
|-----------|---------|
| VoiceForge application code (`app/`, `scripts/`, `docker/`, `tests/`) | MIT — see `LICENSE` |

## Engine model weights (downloaded at runtime — not shipped in git)

| Engine id | Model / stack | Typical license | Commercial use? |
|-----------|---------------|-----------------|-----------------|
| `openvoice-v2` | OpenVoice V2 voice conversion (MyShell, via Coqui) | MIT | Yes (VC weights) |
| `openvoice-v2` | YourTTS base TTS (used to generate speech before VC) | Check Coqui / model card | Verify before commercial use |
| `f5-tts` | F5-TTS v1 base (SWivid) | Apache-2.0 / CC (see upstream) | Generally yes — confirm upstream |
| `xtts-v2` | XTTS-v2 (Coqui) | **CPML — non-commercial / research only** | **No** |
| `rvc` | RVC architecture / trained per-voice checkpoints | MIT (architecture); your trained weights are yours | Yes for architecture; respect base TTS used for synth |
| `chatterbox` | Resemble AI Chatterbox | MIT | Yes |
| `qwen3-tts` | Qwen3-TTS-12Hz-1.7B-Base | Apache-2.0 | Yes |
| `fish-speech` | Fish Speech open weights (self-hosted sidecar) | Check fish-speech / Fish Audio upstream | Verify — not the Fish Audio cloud API |
| `cosyvoice-3` | Fun-CosyVoice3-0.5B | Apache-2.0 | Yes |
| `indextts-2` | IndexTTS-2 (IndexTeam) | Check IndexTTS upstream | Verify before commercial use |

Always re-check the upstream model card before production or commercial use.
`GET /v1/engines` exposes each engine's `capabilities.license` string for UIs.

## Optional RVC worker dependencies

The isolated RVC worker venv (`requirements-rvc.txt`, GPU Docker image) may
install:

| Package / source | Notes |
|------------------|-------|
| `rvc-python` (PyPI) | Inference helper; see package metadata |
| `fairseq` (PyPI) | Meta AI — typically MIT |
| `git+https://github.com/nakshatra-garg/rvc-no-gui.git` | Training pipeline used only in the **isolated** RVC worker (not the main app venv). Review that repo's license before redistributing images that vendor it. |

Main app dependencies are pinned on PyPI / the official PyTorch wheel index.
The RVC worker is the **only** path that intentionally uses a git URL.

## Test fixture audio

`scripts/fixtures/f5_reference_en.wav` is synthetic speech generated for
automated e2e tests (not a recording of a real person).

## Responsible use

Voice cloning can produce convincing audio of real people. Only clone voices
you have the legal right to clone. This project requires `consent=true` on
voice creation; that is an application control, not a substitute for law.
