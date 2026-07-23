# Engine and model licensing

**VoiceForge application code** (`app/`, `scripts/`, `docker/`, `tests/`) is
**MIT** — see [LICENSE](../LICENSE).

Speech engines, library implementations, and **model weights** often use
different terms. “Open-source voice cloning service” does **not** mean every
weight is OSI open source or commercially usable.

This document summarizes what the repository discloses. It is **not legal
advice**. Always re-check upstream model cards before production or commercial
use. `GET /v1/engines` exposes each engine’s `capabilities.license` string for UIs.

## Quick matrix

| Engine ID | Adapter code (this repo) | Engine / library (typical) | Model weights (typical) | Commercial use? | Redistribution of weights | Attribution | Downloaded separately? | Explicit acceptance |
|-----------|--------------------------|----------------------------|-------------------------|-----------------|---------------------------|-------------|------------------------|---------------------|
| `openvoice-v2` | MIT | coqui-tts / OpenVoice VC stack | OpenVoice VC: MIT; YourTTS base: verify Coqui card | VC: generally yes; verify base | Follow upstream | Follow upstream | Yes (runtime) | No special flag beyond general Coqui usage |
| `f5-tts` | MIT | F5-TTS (Apache-2.0 / CC — see upstream) | Apache-2.0 / CC (see SWivid/F5-TTS) | Usually yes — confirm | Follow upstream | Follow upstream | Yes | No |
| `xtts-v2` | MIT | `coqui-tts` library often MPL-2.0 | **CPML — non-commercial / research** | **No** (weights) | Restricted by CPML | CPML terms | Yes (~2GB) | `COQUI_TOS_AGREED=1` for non-interactive download |
| `rvc` | MIT | RVC architecture / worker tools | Architecture MIT; your fine-tune is yours; base TTS may differ | Architecture: generally yes; respect base TTS | Worker may vendor git tooling — review | Follow upstream | Base weights + your train | Review worker deps |
| `chatterbox` | MIT | Resemble AI Chatterbox (MIT) | MIT (per NOTICE) | Yes (per NOTICE) | Follow upstream | Follow upstream | Yes | No |
| `qwen3-tts` | MIT | qwen-tts | Apache-2.0 (per NOTICE / adapter) | Yes (per NOTICE) | Follow upstream | Follow upstream | Yes | No |
| `fish-speech` | MIT | fish-speech sidecar | Check fish-speech / Fish Audio upstream | Verify | Follow upstream | Follow upstream | Sidecar checkpoints | No VoiceForge cloud ToS |
| `cosyvoice-3` | MIT | Fun-CosyVoice worker | Apache-2.0 (per NOTICE) | Yes (per NOTICE) | Follow upstream | Follow upstream | Yes | No |
| `indextts-2` | MIT | IndexTTS worker | Check IndexTeam upstream | Verify | Follow upstream | Follow upstream | Yes | No |

## Distinctions to keep clear

1. **Adapter code** — VoiceForge wrapper under MIT.
2. **Engine implementation** — upstream Python package / worker.
3. **Model weights** — binary checkpoints downloaded at runtime (not shipped in git).
4. **Commercial-use status** — often gated by **weights**, not by MIT on this repo.
5. **Redistribution** — do not commit multi-GB weights; follow upstream.
6. **Attribution** — some projects require NOTICE / citation in products.
7. **Download source** — Hugging Face / Coqui / upstream scripts via
   `scripts/download_models.py` and engine loaders.
8. **Explicit acceptance** — XTTS/CPML uses `COQUI_TOS_AGREED` for non-interactive installs.

## RVC worker note

The isolated RVC worker may install packages from PyPI and a git URL
(`rvc-no-gui`). Review that repository’s licence before redistributing images
that vendor it. See [NOTICE.md](../NOTICE.md).

## Test fixture audio

`scripts/fixtures/f5_reference_en.wav` is **synthetic** speech for automated
tests — not a recording of a real person (see NOTICE).
