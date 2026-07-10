# VoiceForge

A local-first, open-source, multi-engine voice cloning service. Record or
upload a short sample, clone the voice, and turn arbitrary text into speech —
entirely on hardware you control, no cloud TTS vendor, no API keys, no
per-character billing.

Built as a standalone service consumed over HTTP by anything (a web app, a
CLI, curl) — including [Reel Studio](#reel-studio-integration), but with no
dependency on it.

## Status

Milestones **M0–M7** are complete (see [Roadmap](#roadmap)). M6 lives in the
client (e.g. Reel Studio); this repo is the cloning API.

- Full service scaffold: FastAPI, SQLite, bearer auth, CORS, jobs, SSE,
  metrics, optional synth watermark, GitHub CI.
- Zero-shot engines: **OpenVoice V2** (MIT VC), **F5-TTS** (Apache/CC),
  **XTTS-v2** (CPML — non-commercial). Pick per voice via `engine_id`.
- High-fidelity: **RVC** (`tier=high_fidelity`, GPU + isolated worker).
- CPU and GPU Docker images; model pre-download + e2e smoke tests.

**CPU tip:** OpenVoice is the lightest zero-shot path. XTTS / F5 / RVC are
much happier on a GPU session (Lightning AI, RunPod, etc.) — see
[Deploy on Lightning AI / GPU clouds](#deploy-on-lightning-ai--gpu-clouds).

## Mission & non-negotiables

- **100% local-first.** No cloud vendor, no API keys required, no rate
  limits. Runs on a dev machine or a self-hosted VPS/GPU box.
- **Audio-only cloning.** No video processing.
- **Multi-engine, pluggable.** One interface (`CloneEngine`), implemented
  once per engine, selected per voice.
- **API-first.** Every capability is exposed over HTTP.
- **Non-commercial / demo project.** Built for a portfolio, not a SaaS. Some
  engines (XTTS-v2) carry non-commercial model licenses — see
  [Licensing & responsible use](#licensing--responsible-use).
- **GPU available, CPU fallback.** Everything also runs on CPU, just slower.

## Architecture

```
┌─────────────────────┐        HTTP (REST + SSE)        ┌───────────────────────────┐
│   Reel Studio (or    │ ───────────────────────────────▶│  VoiceForge service        │
│   any other client)  │◀─────────────────────────────── │  (FastAPI, Python)         │
└─────────────────────┘        WAV bytes / JSON          │                             │
                                                          │  ┌───────────────────────┐  │
                                                          │  │ Engine registry        │  │
                                                          │  │ (pluggable)            │  │
                                                          │  └──────────┬────────────┘  │
                                                          │             │               │
                                                          │             ▼               │
                                                          │          XTTS-v2, F5-TTS,   │
                                                          │          OpenVoice V2, RVC  │
                                                          │                             │
                                                          │  SQLite (voice metadata)     │
                                                          │  data/ (samples, artifacts)  │
                                                          └───────────────────────────┘
```

Single Python process (FastAPI + Uvicorn), `asyncio` background tasks for
voice processing, SQLite for metadata, and a `data/` directory on disk for
audio samples and per-voice artifacts (cached conditioning latents, etc.).

### The `CloneEngine` interface

Every engine implements one interface (`app/engines/base.py`); the API and
job runner talk only to it, never to a vendor SDK directly:

```python
class CloneEngine(Protocol):
    id: str
    label: str
    capabilities: CloneCapabilities

    def is_ready(self) -> bool: ...
    async def create_voice(self, voice_id, sample_paths, tier, language, on_progress=None) -> VoiceArtifact: ...
    async def synthesize(self, voice_id, artifact, text, opts) -> bytes: ...
```

Adding a new engine = one new file in `app/engines/` + one entry in
`app/engines/registry.py`. Nothing else changes.

## Quickstart (Docker)

```bash
cp .env.example .env
# Edit .env: set VOICEFORGE_API_TOKEN if this will be reachable beyond
# localhost. Leave it empty for pure local dev.

# CPU (works anywhere, no GPU required):
docker compose -f docker/docker-compose.yml --profile cpu up --build

# GPU (requires the NVIDIA Container Toolkit on the host):
docker compose -f docker/docker-compose.yml --profile gpu up --build
```

The first request that touches an ML engine may download large checkpoints
(cached in the `models-cache` Docker volume afterwards). To pre-download all
engine models instead of waiting on the first API request:

```bash
docker compose -f docker/docker-compose.yml --profile cpu run --rm voiceforge-download
```

End-to-end smoke test (service must be running; run from a dev venv):

```bash
docker compose -f docker/docker-compose.yml --profile cpu up --build -d
python scripts/e2e_smoke_test.py --engine openvoice-v2
python scripts/e2e_smoke_test.py --engine xtts-v2
python scripts/e2e_smoke_test.py --engine f5-tts
```

Then:

```bash
curl http://localhost:8089/healthz

curl -H "Authorization: Bearer $VOICEFORGE_API_TOKEN" \
  -F "name=My Voice" -F "engine_id=xtts-v2" -F "tier=instant" \
  -F "consent=true" -F "files=@sample.wav" \
  http://localhost:8089/v1/voices

curl -H "Authorization: Bearer $VOICEFORGE_API_TOKEN" \
  http://localhost:8089/v1/voices/<id>   # poll until status == "ready"

curl -H "Authorization: Bearer $VOICEFORGE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"voiceId": "<id>", "text": "Hello from my cloned voice."}' \
  http://localhost:8089/v1/synthesize -o out.wav
```

Interactive API docs: `http://localhost:8089/docs`.

### CPU vs. GPU

| | CPU (`Dockerfile.cpu`) | GPU (`Dockerfile.gpu`) |
|---|---|---|
| Works on | Any host, incl. a cheap VPS | Host with an NVIDIA GPU + Container Toolkit |
| XTTS-v2 synthesis | Several seconds per sentence | Sub-second to a few seconds |
| Verified in this repo's own testing | ✅ Full e2e (all three engines) via `scripts/e2e_smoke_test.py` | ⚠️ Written and reviewed carefully, but **not** run against a real GPU while building this — no GPU was available. Please verify on your hardware. RVC requires the GPU image. |

### RVC setup (high-fidelity tier)

RVC training uses **fairseq** and **numpy&lt;2**, which conflict with
coqui-tts in the main VoiceForge venv. Training/inference therefore run in an
**isolated worker venv** (`/opt/rvc-venv` in the GPU Docker image, or install
manually from `requirements-rvc.txt`).

```bash
# GPU Docker (recommended) — worker venv is pre-installed:
docker compose -f docker/docker-compose.yml --profile gpu up --build

# Create a high-fidelity RVC voice (≥3 min of clean speech recommended):
curl -F "name=Studio Voice" -F "engine_id=rvc" -F "tier=high_fidelity" \
  -F "consent=true" -F "files=@vocals.wav" http://localhost:8089/v1/voices

# Upgrade an existing voice to high-fidelity (re-trains if engine supports it):
curl -X POST http://localhost:8089/v1/voices/<id>/upgrade

# Pre-download RVC base weights (HuBERT, RMVPE):
docker compose -f docker/docker-compose.yml --profile gpu run --rm voiceforge-download --engine rvc
```

Set `VOICEFORGE_RVC_PYTHON=/path/to/rvc-venv/bin/python` when running outside
the GPU image. Tune training with `VOICEFORGE_RVC_EPOCHS` (default `50`) and
`VOICEFORGE_RVC_BATCH_SIZE` (default `4`).

## API reference

Full interactive docs at `/docs`. Summary:

```
GET  /healthz                        -> { status, service, version, enginesReady, enginesTotal }  (no auth)
GET  /v1/metrics                     -> { uptimeSeconds, voicesCreated, synthRequests, ... }     (auth)

GET  /v1/engines                     -> [{ id, label, capabilities, ready, configured }]

POST /v1/voices                      (multipart/form-data)
     fields: name, engine_id, tier ("instant" | "high_fidelity"),
             consent=true (required), language, files[] (audio)
     -> { id, name, engineId, tier, status, ... }

GET  /v1/voices                      -> [VoiceSummary]
GET  /v1/voices/{id}                 -> VoiceDetail (incl. errorMessage, readyAt)
DELETE /v1/voices/{id}                -> 204, deletes voice + samples + artifacts

POST /v1/voices/{id}/samples         (multipart) -> add more reference audio
POST /v1/voices/{id}/upgrade         -> re-train at high_fidelity tier (fine-tunable engines)
GET  /v1/voices/{id}/events          (SSE)       -> processing progress events
GET  /v1/voices/{id}/preview         -> a short cached WAV clip

POST /v1/synthesize
     body: { voiceId, text, sampleRate?, speed?, language? }
     -> audio/wav bytes
```

Every `/v1/*` route requires `Authorization: Bearer <VOICEFORGE_API_TOKEN>`
**when a token is configured**. See [Security](#security).

## Configuration

All settings are environment variables, prefixed `VOICEFORGE_` (see
`.env.example` for the full list with defaults):

| Variable | Purpose |
|---|---|
| `VOICEFORGE_API_TOKEN` | Bearer token required on `/v1/*`. Required beyond localhost. |
| `VOICEFORGE_CORS_ORIGINS` | Comma-separated allowed browser origins. |
| `VOICEFORGE_DATA_DIR` / `VOICEFORGE_MODELS_DIR` | Where samples/DB and model checkpoints live. |
| `VOICEFORGE_DEVICE` | `cpu`, `cuda`, or `auto`. |
| `VOICEFORGE_MAX_UPLOAD_MB` / `_MAX_SAMPLES_PER_VOICE` / `_MAX_SYNTH_CHARS` | Abuse/resource-exhaustion limits. |
| `VOICEFORGE_PREPROCESS_SAMPLES` | Trim/normalize reference uploads before cloning (default: true). |
| `VOICEFORGE_LOG_FORMAT` | `text` (default) or `json` for structured log lines. |
| `VOICEFORGE_WATERMARK_ENABLED` | Mix a quiet voice-specific fingerprint into synth output (default: false). |
| `VOICEFORGE_WATERMARK_STRENGTH` | Watermark amplitude 0–1 (default: `0.004`). |
| `COQUI_TOS_AGREED` | Non-interactive acceptance of Coqui's CPML for the XTTS-v2 checkpoint download. See licensing below. |

## Security

This is a local-first tool, but it's built defensively since it's designed
to be exposed on a home network / VPS:

- **Auth:** single bearer token (`VOICEFORGE_API_TOKEN`), compared in
  constant time (`secrets.compare_digest`), required on every `/v1/*` route
  when set. The app logs a loud warning at startup if it's unset (dev/pure
  localhost use only — you are responsible for not exposing an
  unauthenticated instance).
- **CORS:** locked to an explicit origin allowlist (`VOICEFORGE_CORS_ORIGINS`);
  empty by default (no cross-origin browser access at all).
- **Upload validation:** every uploaded file is sniffed as real audio via
  `libsndfile` (not trusted by extension/Content-Type), size-capped
  (`VOICEFORGE_MAX_UPLOAD_MB`), duration-bounded, and count-capped per voice.
  Filenames are never used to build filesystem paths — every stored file
  gets a server-generated UUID name, which rules out path traversal via a
  crafted upload filename.
- **Resource limits:** a global semaphore (`VOICEFORGE_MAX_CONCURRENT_JOBS`,
  default 1) caps concurrent heavy ML jobs so one CPU-only or small-GPU host
  can't be overwhelmed by concurrent requests; text length is capped for
  `/synthesize`.
- **Checkpoint loading:** cached conditioning-latent tensors are loaded with
  `torch.load(..., weights_only=True)` — these files only ever contain
  tensors this service wrote itself, so arbitrary pickle deserialization is
  never enabled.
- **Docker:** both images run as a non-root user, install only the OS
  packages actually needed (`libsndfile1`, `ffmpeg`, `curl`), and ship a
  `HEALTHCHECK`.
- **Dependencies:** core and zero-shot engine deps are version-pinned
  (`requirements*.txt` / `pyproject.toml`) from PyPI or the official
  PyTorch wheel index, and re-checked with `pip-audit` (see
  [Development](#development)). The **optional RVC worker** may install
  one git dependency (`rvc-no-gui`) into an isolated venv only — see
  `NOTICE.md`.

**Known accepted risk:** `torch==2.8.0` (the newest version confirmed
compatible with `coqui-tts` without requiring the extra `torchcodec`
dependency at `torch>=2.9`) has a small number of open, low-severity PyTorch
advisories (e.g. `GHSA-c678-jfcj-6jmf`, `GHSA-f4hp-rmr7-r7v8`,
`GHSA-x3gm-94wq-g975`, `GHSA-rrmf-rvhw-rf47`). All require local/authenticated
access and direct invocation of specific low-level APIs
(`torch.jit.script`, `pad_packed_sequence`, quantized ops, JIT futures) that
this service's request-handling code never calls. If you have a strict
compliance requirement, upgrade to `torch>=2.9`/`2.10` and add the
`torchcodec` dependency yourself (see `requirements-xtts.txt`).

## Licensing & responsible use

- **This repository's code** is MIT-licensed (`LICENSE`).
- **Model weights are separate** — see **`NOTICE.md`** for the full table.
  Short version:
  | Engine | Weights license (typical) | Commercial? |
  |--------|---------------------------|-------------|
  | `openvoice-v2` | OpenVoice VC: MIT; YourTTS base: verify Coqui card | VC yes; verify base |
  | `f5-tts` | Apache-2.0 / CC (upstream) | Usually yes — confirm |
  | `xtts-v2` | **CPML — non-commercial / research only** | **No** |
  | `rvc` | RVC architecture MIT; your fine-tune is yours | Yes (architecture) |
- Application controls (not a substitute for law):
  - Every voice creation requires `consent: true`.
  - `GET /v1/engines` exposes `capabilities.license` for client UIs.
- This is a **voice-cloning tool** — only clone voices you have the right to
  clone.

## Development

Requires Python 3.11+ (the ML stack is verified against 3.11 specifically,
matching the Docker images).

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                    # core + dev tooling, no ML stack
pip install -r requirements-xtts.txt -r requirements-f5.txt \
  --extra-index-url https://download.pytorch.org/whl/cpu  # both engines locally

pytest                 # full test suite (mocks the ML engine — no GPU/torch download required)
ruff check app tests scripts
pip-audit              # dependency vulnerability scan

# Optional: score a clone (speaker similarity + WER) — needs torch + benchmark extras:
pip install -e ".[xtts,benchmark]"
python scripts/benchmark_quality.py \\
  --reference sample.wav --generated synth.wav \\
  --text "The sentence that was synthesized."
```

Tests never require torch/coqui-tts: a lightweight in-memory `FakeEngine`
(pure numpy/soundfile) is registered alongside the real `xtts-v2` engine so
the API, DB, validation, and auth layers are fully exercised without a
multi-GB model download. The XTTS-v2 engine itself was verified separately,
end-to-end, inside the CPU Docker image (real upload → clone → synthesize →
valid WAV output).

## Roadmap

- [x] **M0 — Scaffold:** FastAPI skeleton, `/healthz`, SQLite models, Docker
      CPU image, engine registry, README.
- [x] **M1 — MVP clone (XTTS-v2):** upload/record → instant zero-shot voice
      → `/synthesize` returns WAV. Manually + automatically verified.
- [x] **M2 — Quality benchmarking:** `scripts/benchmark_quality.py`
      (speaker-similarity + WER), reference-audio preprocessing on upload.
- [x] **M3a — F5-TTS engine:** permissive-license zero-shot engine behind
      `CloneEngine`.
- [x] **M3b — OpenVoice V2 engine:** MIT-licensed zero-shot engine (Coqui VC
      + YourTTS base) behind `CloneEngine`.
- [x] **M4 — High-fidelity tier:** RVC training pipeline (isolated worker),
      SSE training-progress events, `POST /v1/voices/{id}/upgrade` flow.
- [x] **M5 — Docker hardening:** GPU + CPU images, model-cache volume,
      `voiceforge-download` compose service, `scripts/e2e_smoke_test.py`
      (CPU e2e verified for openvoice-v2, xtts-v2, f5-tts).
- [x] **M6 — Reel Studio integration:** `VoiceProvider` + clone UI in the
      client repo (verified); see
      [Integrating with Reel Studio or any custom app](#integrating-with-reel-studio-or-any-custom-app).
- [x] **M7 — Polish & release:** GitHub CI, structured JSON logging,
      `/v1/metrics`, enhanced `/healthz`, optional synth watermarking,
      OpenAPI tag docs, `NOTICE.md` / `SECURITY.md` (v0.2.0).

## Integrating with Reel Studio or any custom app

VoiceForge is a **standalone HTTP service**. Reel Studio (or any other app)
talks to it over REST + SSE — no shared code, no merged Docker compose
required. M6 is implemented **in the client repo** (e.g. a new
`VoiceProvider` in Reel Studio); this repo only runs the cloning API.

### Architecture

```
┌─────────────────────┐     HTTP (server-side)      ┌─────────────────────────┐
│  Reel Studio        │  VOICEFORGE_SERVICE_URL     │  VoiceForge (this repo) │
│  Next.js server     │ ──────────────────────────▶ │  :8089                  │
│  voiceforge.ts      │  Bearer token (optional)    │  FastAPI + ML engines   │
└─────────────────────┘                             └─────────────────────────┘
         ▲
         │ browser (optional clone UI — prefer proxy via Next API route)
         └──────────────────────────────────────────────────────────────
```

- **List voices / synthesize:** call VoiceForge from your **backend** (Reel
  Studio's `VoiceProvider.synth()` pattern) — no browser CORS issues.
- **Clone upload from browser:** either set `VOICEFORGE_CORS_ORIGINS` or (recommended)
  add a Next.js API route that proxies multipart uploads so the token stays
  on the server.

---

### Step 1 — Start VoiceForge

**Docker (recommended):**

```bash
cd /path/to/audio-cloning
cp .env.example .env
# Optional but recommended if Reel Studio or other clients send a token:
# VOICEFORGE_API_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Pre-download models (first run otherwise downloads multi-GB on first request):
docker compose -f docker/docker-compose.yml --profile cpu run --rm voiceforge-download

# Start the API (CPU — works everywhere; GPU profile for RVC / faster synth):
docker compose -f docker/docker-compose.yml --profile cpu up -d --build
```

**Verify:**

```bash
curl http://localhost:8089/healthz
# -> {"status":"ok","service":"voiceforge","version":"0.2.0","enginesReady":3,...}

open http://localhost:8089/docs   # interactive OpenAPI
```

Default base URL: **`http://localhost:8089`**

---

### Step 2 — Configure auth and CORS

| Scenario | What to set |
|----------|-------------|
| Local dev, server-to-server only | Leave `VOICEFORGE_API_TOKEN` empty; Reel Studio calls from Node without auth. |
| Token required | Same token in VoiceForge `.env` and Reel Studio `VOICEFORGE_API_TOKEN`. |
| Browser uploads directly to VoiceForge | Add Reel Studio origin to `VOICEFORGE_CORS_ORIGINS=http://localhost:3000` |

Generate a token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

### Step 3 — Smoke-test the API (curl)

**List engines** (pick `engine_id` + read `capabilities.license` for UI):

```bash
curl -s http://localhost:8089/v1/engines | python3 -m json.tool
```

**Create a cloned voice** (instant zero-shot example with OpenVoice):

```bash
curl -s -X POST http://localhost:8089/v1/voices \
  -H "Authorization: Bearer $VOICEFORGE_API_TOKEN" \
  -F "name=Demo Clone" \
  -F "engine_id=openvoice-v2" \
  -F "tier=instant" \
  -F "consent=true" \
  -F "language=en" \
  -F "files=@reference.wav" \
  | python3 -m json.tool
```

**Poll until ready** (or use SSE — next section):

```bash
curl -s http://localhost:8089/v1/voices/<voice_id> \
  -H "Authorization: Bearer $VOICEFORGE_API_TOKEN"
```

**Synthesize:**

```bash
curl -s -X POST http://localhost:8089/v1/synthesize \
  -H "Authorization: Bearer $VOICEFORGE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"voiceId":"<voice_id>","text":"Hello from VoiceForge."}' \
  -o out.wav
```

Or run the bundled e2e script (from a dev venv with `httpx`):

```bash
pip install -e ".[dev]"
python scripts/e2e_smoke_test.py --engine openvoice-v2
```

---

### Step 4 — Wire Reel Studio (env vars)

In the **reel-studio** repo `.env.local`:

```bash
VOICEFORGE_SERVICE_URL=http://localhost:8089
VOICEFORGE_API_TOKEN=          # same as VoiceForge .env when set; empty for open localhost dev
```

Reel Studio already documents the provider pattern in
`docs/voice-clone-service-BRIEF.md` §11. Implementation lives entirely in
reel-studio — **not in this repo**.

---

### Step 5 — What to build in Reel Studio (M6 checklist)

| File / area | Action |
|-------------|--------|
| `src/providers/voice/types.ts` | Add `"voiceforge"` to `PROVIDER_IDS`. |
| `src/providers/voice/voiceforge.ts` | New `VoiceProvider`: `listVoices`, `listModels`, `synth`. |
| `src/providers/voice/registry.ts` | Register `createVoiceforgeProvider`. |
| `.env.example` | Document `VOICEFORGE_SERVICE_URL`, `VOICEFORGE_API_TOKEN`. |
| Clone UI (new route or `/voices` panel) | Record/upload → `POST /v1/voices` → SSE progress → voice appears in browser. |
| Optional API proxy | `src/app/api/voiceforge/...` to proxy clone uploads without exposing token to the browser. |

**Provider mapping (VoiceForge → Reel Studio):**

| VoiceForge | Reel Studio `VoiceProvider` |
|------------|----------------------------|
| `GET /v1/voices` | `listVoices()` → map each to `{ id, name, category: "cloned", previewUrl }` |
| `GET /v1/voices/{id}/preview` | prefix with `VOICEFORGE_SERVICE_URL` for `previewUrl` |
| `GET /v1/engines` | `listModels()` → `{ id: engine.id, label: engine.label }` |
| `POST /v1/synthesize` JSON `{ voiceId, text, ... }` | `synth()` → parse WAV with `parseWav` from `@/lib/wav` |
| `POST /v1/voices` multipart | Clone UI only (not part of `VoiceProvider`) |

Use `providerFetch()` from `src/providers/voice/http.ts` for consistent errors.
Set `maxConcurrency: 1` (CPU-bound local ML, same as `kokoro-server`).

**Engine choice for cloning (surface in UI):**

| `engine_id` | Tier | License | Notes |
|-------------|------|---------|-------|
| `openvoice-v2` | `instant` | MIT | Good default; fast zero-shot |
| `f5-tts` | `instant` | Apache/CC | Needs intelligible speech in reference |
| `xtts-v2` | `instant` | CPML | Non-commercial only |
| `rvc` | `high_fidelity` | MIT | GPU + long reference audio; training takes minutes |

---

### Step 6 — SSE progress (clone UI)

Subscribe while a voice is processing:

```bash
curl -N -H "Authorization: Bearer $VOICEFORGE_API_TOKEN" \
  http://localhost:8089/v1/voices/<voice_id>/events
```

Events:

- `event: progress` — `data: {"type":"progress","message":"loading_model",...}`
- `event: status` — `data: {"status":"ready"}` or `"failed"` with error details

In the browser, use `EventSource` (with a Next.js proxy if you need auth
headers — native `EventSource` cannot set `Authorization`).

---

### Step 7 — Integrate from any other app (minimal examples)

**TypeScript (Node 18+):**

```typescript
const base = process.env.VOICEFORGE_SERVICE_URL ?? "http://localhost:8089";
const headers = {
  Authorization: `Bearer ${process.env.VOICEFORGE_API_TOKEN ?? ""}`,
};

// List cloned voices
const voices = await fetch(`${base}/v1/voices`, { headers }).then((r) => r.json());

// Synthesize
const wav = await fetch(`${base}/v1/synthesize`, {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ voiceId: voices[0].id, text: "Hello world." }),
}).then((r) => r.arrayBuffer());
```

**Python:**

```python
import httpx, os

base = os.environ.get("VOICEFORGE_SERVICE_URL", "http://localhost:8089")
token = os.environ.get("VOICEFORGE_API_TOKEN", "")
headers = {"Authorization": f"Bearer {token}"} if token else {}

with httpx.Client(base_url=base, headers=headers, timeout=600.0) as client:
    voices = client.get("/v1/voices").json()
    wav = client.post("/v1/synthesize", json={
        "voiceId": voices[0]["id"],
        "text": "Hello world.",
    }).content
    open("out.wav", "wb").write(wav)
```

JSON field names on the wire are **camelCase** (`voiceId`, `engineId`,
`errorMessage`) to match Reel Studio conventions.

---

### Cursor agent prompt for Reel Studio (copy-paste)

Open the **reel-studio** project in Cursor and start a new agent chat with:

---

**Implement M6 — VoiceForge voice cloning provider**

VoiceForge is running at `http://localhost:8089` (OpenAPI at `/docs`). Implement integration per `docs/voice-clone-service-BRIEF.md` §11 and the VoiceForge README section "Integrating with Reel Studio".

**Tasks:**

1. Add `"voiceforge"` to `PROVIDER_IDS` in `src/providers/voice/types.ts`.
2. Create `src/providers/voice/voiceforge.ts` implementing `VoiceProvider`:
   - `id: "voiceforge"`, `label: "VoiceForge (local clone)"`, `runtime: "server"`, `keyless: true` when only `VOICEFORGE_SERVICE_URL` is set (use bearer token from `VOICEFORGE_API_TOKEN` when present).
   - `isConfigured()` → `VOICEFORGE_SERVICE_URL` is set.
   - `listModels()` → `GET {base}/v1/engines` → `{ id, label }[]`.
   - `listVoices()` → `GET {base}/v1/voices`, filter `status === "ready"`, map to `VoiceSummary` with `category: "cloned"`, `previewUrl: {base}/v1/voices/{id}/preview`.
   - `synth(opts)` → `POST {base}/v1/synthesize` with `{ voiceId, text, sampleRate, speed, language }`, parse WAV via `parseWav` like `cartesia.ts`.
   - `maxConcurrency: 1`.
   - Use `providerFetch()` from `./http`.
3. Register in `src/providers/voice/registry.ts`.
4. Add `VOICEFORGE_SERVICE_URL` and `VOICEFORGE_API_TOKEN` to `.env.example`.
5. Add a **Clone a voice** UI (new page or section on `/voices`):
   - File upload + optional mic record (`MediaRecorder`).
   - Engine dropdown from `/v1/engines`, tier `instant` vs `high_fidelity`, consent checkbox.
   - Submit `POST /v1/voices` (prefer a Next.js API route proxy so the bearer token is not exposed to the browser).
   - Show progress via SSE (`GET /v1/voices/{id}/events`) or polling.
   - On `ready`, refresh voice list so the new voice appears under VoiceForge in the voice browser and voiceover panel.
6. Tests: extend `src/providers/voice/providers.test.ts` with mocked fetch for voiceforge (mirror cartesia/elevenlabs tests).

**Do not** merge VoiceForge's docker-compose into reel-studio — two separate services linked by URL only.

Reference existing providers: `kokoro-server.ts`, `cartesia.ts`, `elevenlabs.ts`.

---

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `503 Engine not ready` | Run `voiceforge-download`; first request downloads models. |
| `401 Missing bearer token` | Set matching `VOICEFORGE_API_TOKEN` on both services. |
| CORS error from browser | Use a Next.js proxy route, or set `VOICEFORGE_CORS_ORIGINS`. |
| `422 tier=instant` on RVC | RVC requires `tier=high_fidelity`. |
| Reel Studio can't reach service | Use `host.docker.internal:8089` if Reel Studio runs in Docker on Mac/Windows. |
| Slow synthesis on CPU | Expected; use GPU compose profile or pick lighter engines. |

---

## Deploy on Lightning AI / GPU clouds

VoiceForge is a normal Docker/HTTP service — it fits session-based GPU
providers (Lightning AI, RunPod, Vast, etc.) the same way as any FastAPI app.

### Recommended setup on Lightning AI

1. **Create a GPU Studio / job** with an NVIDIA GPU and Docker (or a Python
   environment with CUDA).
2. **Clone this repo** into the session (do not upload your local `data/`
   folder — it may contain personal voice samples).
3. **Start with the GPU image** (or install deps + set `VOICEFORGE_DEVICE=cuda`):

```bash
cp .env.example .env
# Required when the session is reachable from the internet:
# VOICEFORGE_API_TOKEN=<long random secret>
# VOICEFORGE_CORS_ORIGINS=https://your-reel-studio-origin   # if browser calls directly

docker compose -f docker/docker-compose.yml --profile gpu up --build -d
# or: docker compose ... --profile gpu run --rm voiceforge-download
```

4. **Expose port `8089`** via the provider's public URL / proxy.
5. **Point Reel Studio** (or any client) at that URL:

```bash
VOICEFORGE_SERVICE_URL=https://<your-lightning-proxy-host>
VOICEFORGE_API_TOKEN=<same token as on the GPU session>
```

6. **When the session ends**, treat `data/` as disposable (cloned voices and
   SQLite live there). Re-download models on the next session or attach a
   persistent volume to `/app/models` if the provider supports it.

### Engine choice on free GPU hours

| Goal | Engine | Why |
|------|--------|-----|
| Fastest / lightest | `openvoice-v2` | Works on CPU; still fine on GPU |
| Best zero-shot quality (permissive) | `f5-tts` | Happier on GPU |
| Multilingual zero-shot | `xtts-v2` | GPU recommended; **CPML non-commercial** |
| Highest fidelity | `rvc` + `high_fidelity` | Needs GPU + longer reference audio |

### Session hygiene

- Always set `VOICEFORGE_API_TOKEN` on public endpoints.
- Never commit `.env` or `data/`.
- Wipe or unmount voice data before sharing a Studio snapshot.

---

## Reel Studio integration (summary)

M6 code changes belong in the **reel-studio** repository. VoiceForge exposes
a stable HTTP API (documented above and at `/docs`). Follow the Cursor prompt
in the previous section to implement the provider and clone UI there.

## Repo layout

```
voiceforge/
├── app/
│   ├── main.py, config.py, db.py, db_models.py, schemas.py, security.py, storage.py
│   ├── api/          # voices.py, engines.py, synth.py, events.py, metrics.py
│   ├── engines/       # base.py, registry.py, xtts_v2.py, f5_tts.py, openvoice_v2.py, rvc.py
│   └── jobs/          # background processing + SSE event bus
├── docker/            # Dockerfile.cpu, Dockerfile.gpu, docker-compose.yml
├── scripts/           # download_models.py
├── tests/
├── data/              # git-ignored: db.sqlite, voices/{id}/{samples,artifacts}
└── models/            # git-ignored: downloaded model checkpoints
```
