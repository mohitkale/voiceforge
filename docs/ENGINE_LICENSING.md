# Engine and model licensing

**VoiceForge application code** (`app/`, `scripts/`, `docker/`, `tests/`) is
**MIT** — see [LICENSE](../LICENSE).

Speech engines, library implementations, and **model weights** often use
different terms. “Open-source voice cloning service” does **not** mean every
weight is OSI open source or commercially usable.

This document summarizes what the repository discloses. It is **not legal
advice**. Always re-check upstream model cards before production or commercial
use. `GET /v1/providers` exposes structured adapter, implementation, and weight
licence metadata; `GET /v1/engines` retains a compact display string for older
clients.

## Quick matrix

| Engine ID | Adapter code (this repo) | Engine / library (typical) | Model weights (typical) | Commercial use? | Redistribution of weights | Attribution | Downloaded separately? | Explicit acceptance |
|-----------|--------------------------|----------------------------|-------------------------|-----------------|---------------------------|-------------|------------------------|---------------------|
| `openvoice-v2` | MIT | coqui-tts / OpenVoice VC stack | OpenVoice VC: MIT; YourTTS base: verify Coqui card | VC: generally yes; verify base | Follow upstream | Follow upstream | Yes (runtime) | No special flag beyond general Coqui usage |
| `f5-tts` | MIT | F5-TTS code: MIT | **CC-BY-NC-4.0** for the official pretrained weights | **No** for the official weights | Follow CC-BY-NC-4.0 | Required | Yes | No |
| `xtts-v2` | MIT | `coqui-tts` library often MPL-2.0 | **CPML — non-commercial / research** | **No** (weights) | Restricted by CPML | CPML terms | Yes (~2GB) | `COQUI_TOS_AGREED=1` for non-interactive download |
| `rvc` | MIT | RVC architecture / worker tools | Architecture MIT; your fine-tune is yours; base TTS may differ | Architecture: generally yes; respect base TTS | Worker may vendor git tooling — review | Follow upstream | Base weights + your train | Review worker deps |
| `chatterbox` | MIT | Resemble AI Chatterbox (MIT) | MIT | Yes | Follow upstream | Follow upstream | Explicit setup only | No |
| `qwen3-tts` | MIT | qwen-tts | Apache-2.0 (per NOTICE / adapter) | Yes (per NOTICE) | Follow upstream | Follow upstream | Yes | No |
| `fish-speech` | MIT | fish-speech sidecar | **Fish Audio Research License** | **No** unless separately licensed | Restricted | Follow upstream | Operator-managed sidecar | No VoiceForge cloud ToS |
| `cosyvoice-3` | MIT | Fun-CosyVoice worker | Apache-2.0 (per NOTICE) | Yes (per NOTICE) | Follow upstream | Follow upstream | Yes | No |
| `indextts-2` | MIT | IndexTTS worker | Custom Bilibili IndexTTS license | Review upstream terms | Follow upstream | Follow upstream | Yes | No |
| `voxcpm2` | MIT | VoxCPM code: Apache-2.0 | Apache-2.0 | Yes | Follow upstream | Follow upstream | Explicit setup only | No |
| `qwen3-asr` | MIT | qwen-asr: Apache-2.0 | Apache-2.0 | Yes | Follow upstream | Follow upstream | Explicit setup only | No |
| `indicf5` | Manifest only | MIT (model card) | MIT-tagged, but access-gated | Yes under the published license; review gate terms | Follow upstream | Follow upstream | No installer | Model access gate + consent-only cloning terms |
| `indic-parler-tts` | Manifest only | Apache-2.0 | Apache-2.0, but access-gated | Yes under the published license; review gate terms | Follow upstream | Follow upstream | No installer | Model access gate |

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
