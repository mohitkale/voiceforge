# Reel Studio integration

VoiceForge is a **standalone** HTTP voice-cloning service. Reel Studio (or any
app) talks to it over REST + SSE. No shared process and no merged Docker Compose
are required.

```
Reel Studio (scripts, scenes, video)
        │  HTTP (+ optional SSE)
        ▼
VoiceForge API  (/v1/voices, /v1/synthesize, /v1/engines, …)
        │
        ▼
Selected local engine (OpenVoice, F5-TTS, XTTS, …)
        │
        ▼
WAV audio bytes
```

VoiceForge does **not** become a video tool. Reel Studio should **not** absorb
model installation and engine dependency complexity.

## Configure Reel Studio

In the **reel-studio** repo (`.env.local`):

```bash
VOICEFORGE_SERVICE_URL=http://localhost:8089
VOICEFORGE_API_TOKEN=          # same as VoiceForge when set; empty for open localhost
```

If Reel Studio runs in Docker on Mac/Windows and VoiceForge is on the host:

```bash
VOICEFORGE_SERVICE_URL=http://host.docker.internal:8089
```

## Auth and CORS

| Scenario | Setting |
|----------|---------|
| Server-to-server only | Token optional on localhost; required when exposed |
| Matching token | Same value in both services’ env |
| Browser uploads to VoiceForge | Set `VOICEFORGE_CORS_ORIGINS` **or** (preferred) proxy via Next.js so the token stays server-side |

## Expected audio format

`POST /v1/synthesize` returns **16-bit PCM WAV** bytes (`audio/wav`). Clients
parse WAV in-process (Reel Studio’s `parseWav` pattern).

## Engine selection

Clone-time `engine_id` is stored on the voice. Synthesis uses that voice’s
engine. Surface `GET /v1/engines` (and each `capabilities.license`) in UI.

Licence responsibility for commercial products remains with the operator — see
[ENGINE_LICENSING.md](ENGINE_LICENSING.md).

## Failure behaviour

| Symptom | Likely cause |
|---------|--------------|
| Connection refused | VoiceForge not running / wrong URL |
| 401 | Token mismatch |
| 503 engine not ready | Models not downloaded / worker/sidecar missing |
| CORS errors | Browser hitting VoiceForge without allowlist or proxy |
| Slow CPU synth | Expected; pick lighter engines or GPU host |

## Voice deletion implications

Deleting a voice in VoiceForge removes samples and artifacts on the VoiceForge
host. Reel Studio should drop stale voice IDs from any local cache/UI list.

## Provider mapping (client checklist)

| VoiceForge | Typical `VoiceProvider` mapping |
|------------|----------------------------------|
| `GET /v1/voices` | `listVoices()` → cloned voices with preview URL |
| `GET /v1/voices/{id}/preview` | `previewUrl` |
| `GET /v1/engines` | `listModels()` |
| `POST /v1/synthesize` | `synth()` → WAV |
| `POST /v1/voices` | Clone UI only (not required for synth provider) |

JSON field names on the wire are **camelCase** (`voiceId`, `engineId`, …).

## Independence

VoiceForge remains usable with curl, the Studio UI, CLI scripts, and any HTTP
client. Reel Studio is an optional consumer, not a hard dependency.
