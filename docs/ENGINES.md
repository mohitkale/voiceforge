# Engine support matrix

VoiceForge exposes multiple cloning engines behind one `CloneEngine` API.
**Adapters are not equal:** install path, hardware needs, licences, and
verification status differ. Prefer the readiness labels below over assuming
“Docker up ⇒ every engine works.”

> Application code is MIT. Each engine/model has its own terms — see
> [ENGINE_LICENSING.md](ENGINE_LICENSING.md) and root [NOTICE.md](../NOTICE.md).

## Categories

### Easiest starting point

| Engine | Why |
|--------|-----|
| **`openvoice-v2`** | Lightest zero-shot path on CPU; included in default CPU image; CPU e2e verified |

### Higher-quality / heavier zero-shot

| Engine | Notes |
|--------|-------|
| `f5-tts` | CPU e2e verified; needs clear speech (ASR for ref text); GPU preferred for speed |
| `xtts-v2` | CPU e2e verified; **CPML — non-commercial/research**; GPU preferred |
| `chatterbox` | Isolated worker in CPU image; smoke documented; not in verified e2e trio |
| `qwen3-tts` | In-process; ~6GB+ VRAM recommended; smoke documented |

### Advanced / externally managed

| Engine | Notes |
|--------|-------|
| `rvc` | Trained conversion; **GPU required**; isolated worker; not CPU-e2e verified |
| `fish-speech` | Self-hosted HTTP sidecar (`VOICEFORGE_FISH_SPEECH_URL` / compose profile `fish`) |
| `cosyvoice-3` | Isolated worker; GPU recommended; not in default images |
| `indextts-2` | Isolated worker; GPU recommended; verify upstream licence |

Kokoro is **not** a VoiceForge engine (Reel Studio may use a separate kokoro server).

## Support matrix

Statuses used below:

- **Verified** — CPU e2e claimed in-repo via `scripts/e2e_smoke_test.py`
- **Smoke-documented** — README documents a smoke command; broader verification incomplete
- **External sidecar** — readiness depends on a separate process/URL
- **GPU verification needed** — GPU path written; not run on real NVIDIA hardware during development
- **Disabled by default** — needs extra install, env, or profile

| Engine ID | Clone type | CPU | GPU | Default CPU image | Licence note (adapter string) | Verification |
|-----------|------------|-----|-----|-------------------|-------------------------------|--------------|
| `openvoice-v2` | Zero-shot | Yes | Yes | Yes (via coqui stack) | MIT (OpenVoice V2 VC) + YourTTS base (verify Coqui model card) | Verified (CPU e2e) |
| `f5-tts` | Zero-shot | Slow | Recommended | Yes | Apache-2.0 / CC (model weights) — see SWivid/F5-TTS repo | Verified (CPU e2e) |
| `xtts-v2` | Zero-shot | Slow | Recommended | Yes | CPML — non-commercial/research only | Verified (CPU e2e) |
| `chatterbox` | Zero-shot | Yes (worker) | Optional | Yes (`/opt/chatterbox-venv`) | MIT (Resemble AI Chatterbox) | Smoke-documented |
| `qwen3-tts` | Zero-shot | Limited | Recommended | Yes (Dockerfile installs `requirements-qwen3.txt`) | Apache-2.0 (Qwen3-TTS) | Smoke-documented |
| `rvc` | Trained conversion | No (requires GPU) | Required | No — GPU image | MIT (RVC model architecture — see RVC-Project) | GPU verification needed |
| `fish-speech` | Zero-shot via sidecar | Depends on sidecar | Recommended for sidecar | No | Check Fish Audio / fish-speech upstream (open weights; not cloud API) | External sidecar |
| `cosyvoice-3` | Zero-shot | Limited | Recommended (`requires_gpu=True`) | No | Apache-2.0 (Fun-CosyVoice 3.0) | GPU verification needed / extra install |
| `indextts-2` | Zero-shot | Limited | Recommended (`requires_gpu=True`) | No | Check IndexTTS / IndexTeam upstream before commercial use | GPU verification needed / extra install |

## Per-engine detail

### `openvoice-v2`

| | |
|--|--|
| Label | OpenVoice V2 (MyShell, via Coqui VC) |
| Method | Zero-shot (YourTTS base → OpenVoice VC) |
| Reference audio | min ~3s, recommended ~8s |
| Languages (capabilities) | en, es, fr, zh, ja, ko |
| Memory category | ~2 GB VRAM class (`approx_vram_gb=2.0`) |
| Adapter readiness | `is_ready` if VC loaded or `TTS` importable |
| Known limits | Korean YourTTS lang mapped to `en` for cross-lingual VC |

### `f5-tts`

| | |
|--|--|
| Label | F5-TTS v1 (SWivid) |
| Method | Zero-shot; needs reference transcript (Whisper ASR) |
| Reference audio | min ~6s, recommended ~12s; use intelligible speech |
| Languages | en, zh (base training) |
| Memory | ~4 GB VRAM class |
| Fixture | Prefer `scripts/fixtures/f5_reference_en.wav` for automated tests |

### `xtts-v2`

| | |
|--|--|
| Label | XTTS-v2 (Coqui, community fork) |
| Method | Zero-shot |
| Reference audio | min ~6s, recommended ~20s |
| Languages | multilingual list in capabilities |
| Memory | ~4 GB VRAM class |
| Licence | **CPML non-commercial** — set `COQUI_TOS_AGREED=1` for non-interactive download |

### `chatterbox`

| | |
|--|--|
| Method | Zero-shot via isolated worker |
| Env | `VOICEFORGE_CHATTERBOX_PYTHON` (default `/opt/chatterbox-venv/bin/python`) |
| Reason for worker | numpy&lt;2 / torch pins conflict with main coqui stack |

### `qwen3-tts`

| | |
|--|--|
| Method | In-process zero-shot |
| Notes | ~6GB+ VRAM recommended in README; may fall back to x-vector-only mode without transcript |

### `rvc`

| | |
|--|--|
| Method | Fine-tune / high-fidelity conversion (`tier=high_fidelity` only) |
| Reference audio | min ~180s, recommended ~300s |
| Install | GPU image `/opt/rvc-venv`; `requirements-rvc.txt` |
| Limits | Instant tier rejected; training takes minutes |

### `fish-speech`

| | |
|--|--|
| Method | HTTP to self-hosted fish-speech server |
| Config | `VOICEFORGE_FISH_SPEECH_URL` |
| Compose | `--profile fish` |
| Cloud | Does **not** use Fish Audio cloud API keys |

### `cosyvoice-3` / `indextts-2`

| | |
|--|--|
| Method | Isolated worker scripts |
| Env | `VOICEFORGE_COSYVOICE_PYTHON` / `VOICEFORGE_INDEXTTS_PYTHON` |
| Images | Not preinstalled in default CPU/GPU Dockerfiles |

## Hardware honesty

- CPU e2e was verified for **openvoice-v2**, **xtts-v2**, and **f5-tts**.
- The GPU Docker path was written carefully but **not** exercised on real NVIDIA
  hardware during development of this repository. Verify on your own GPU host.
- Do not assume equal quality or speed across engines.
