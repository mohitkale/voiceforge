# VoiceForge

A local-first, open-source, multi-engine voice cloning service. Record or
upload a short sample, clone the voice, and turn arbitrary text into speech —
entirely on hardware you control, no cloud TTS vendor, no API keys, no
per-character billing.

Built as a standalone service consumed over HTTP by anything (a web app, a
CLI, curl) — including [Reel Studio](#reel-studio-integration), but with no
dependency on it.

## Status

This is milestone **M0 + M1** of the project (see [Roadmap](#roadmap)):

- Full service scaffold: FastAPI app, SQLite metadata store, bearer-token
  auth, CORS, background job processing, SSE progress events.
- One fully working, real cloning engine: **XTTS-v2** (zero-shot, instant
  tier) — upload a sample, get a cloned voice, synthesize speech from text.
- CPU and GPU Docker images.

Multi-engine support (F5-TTS, OpenVoice V2), the RVC high-fidelity
fine-tuning pipeline, and the quality-benchmark script are designed for (see
the `CloneEngine` interface below) but not yet implemented — see
[Roadmap](#roadmap).

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
                                                          │          XTTS-v2             │
                                                          │   (more engines: see roadmap)│
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

The first request that touches the XTTS-v2 engine downloads its ~1.9GB
checkpoint (cached in the `models-cache` Docker volume afterwards). To
pre-download it instead of waiting on the first API request:

```bash
docker compose -f docker/docker-compose.yml --profile cpu run --rm \
  voiceforge-cpu python scripts/download_models.py
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
| Verified in this repo's own testing | ✅ Full end-to-end (clone + synthesize) tested | ⚠️ Written and reviewed carefully, but **not** run against a real GPU while building this — no GPU was available. Please verify on your hardware. |

## API reference

Full interactive docs at `/docs`. Summary:

```
GET  /healthz                        -> { status, service }                (no auth)

GET  /v1/engines                     -> [{ id, label, capabilities, ready, configured }]

POST /v1/voices                      (multipart/form-data)
     fields: name, engine_id, tier ("instant" | "high_fidelity"),
             consent=true (required), language, files[] (audio)
     -> { id, name, engineId, tier, status, ... }

GET  /v1/voices                      -> [VoiceSummary]
GET  /v1/voices/{id}                 -> VoiceDetail (incl. errorMessage, readyAt)
DELETE /v1/voices/{id}                -> 204, deletes voice + samples + artifacts

POST /v1/voices/{id}/samples         (multipart) -> add more reference audio
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
- **Dependencies:** every dependency is version-pinned (`requirements*.txt`
  / `pyproject.toml`), checked against the OSV/PyPA advisory databases
  before pinning, and re-checked with `pip-audit` (see
  [Development](#development)). No dependency is installed from an
  unofficial source or a git URL — everything comes from PyPI or the
  official PyTorch wheel index.

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
- **XTTS-v2 model weights** are licensed under Coqui's **CPML (Coqui Public
  Model License) — non-commercial / research use only**. This service is a
  personal, non-commercial, open-source portfolio project; it enforces this
  honestly rather than with a hard legal gate:
  - Every voice creation requires an explicit `consent: true` field
    ("I have the right to use/clone this voice").
  - `GET /v1/engines` reports each engine's `license` field so any client
    (including Reel Studio) can surface it to the end user.
  - **Do not** use the XTTS-v2 engine in this service for any commercial
    purpose. If you need a permissively-licensed engine, see the roadmap
    (F5-TTS / OpenVoice V2 are Apache-2.0 / MIT respectively) — not yet
    implemented in this milestone.
- Consider this a **voice-cloning tool that can produce convincing fake
  audio of real people.** Only clone voices you have the right to clone.

## Development

Requires Python 3.11+ (the ML stack is verified against 3.11 specifically,
matching the Docker images).

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                    # core + dev tooling, no ML stack
pip install -r requirements-xtts.txt \
  --extra-index-url https://download.pytorch.org/whl/cpu  # + XTTS-v2, if you want to run it locally

pytest                 # full test suite (mocks the ML engine — no GPU/torch download required)
ruff check app tests scripts
pip-audit              # dependency vulnerability scan
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
- [ ] **M2 — Quality benchmarking:** `scripts/benchmark_quality.py`
      (speaker-similarity + WER), reference-audio preprocessing.
- [ ] **M3 — Multi-engine:** F5-TTS and OpenVoice V2 behind the same
      interface.
- [ ] **M4 — High-fidelity tier:** RVC training pipeline, SSE
      training-progress events, "upgrade this voice" flow.
- [x] **M5 — GPU packaging:** `Dockerfile.gpu`, GPU compose profile,
      model-cache volume (build verified; hardware not available to run it in
      this environment — see [CPU vs. GPU](#cpu-vs-gpu)).
- [ ] **M6 — Reel Studio integration:** see below.
- [ ] **M7 — Polish & release:** optional audio watermarking, demo media,
      GitHub release notes.

## Reel Studio integration

Not yet implemented (M6). Reel Studio already has a `VoiceProvider`
abstraction (`src/providers/voice/types.ts`); adding VoiceForge there means:
a new `src/providers/voice/voiceforge.ts` implementing that interface
(`listVoices` → `GET /v1/voices`, `listModels` → `GET /v1/engines`, `synth`
→ `POST /v1/synthesize`), registering it in
`src/providers/voice/registry.ts`, and a small "clone a voice" UI flow. The
two services stay independently deployed, connected only over HTTP via
`VOICEFORGE_SERVICE_URL`.

## Repo layout

```
voiceforge/
├── app/
│   ├── main.py, config.py, db.py, db_models.py, schemas.py, security.py, storage.py
│   ├── api/          # voices.py, engines.py, synth.py, events.py
│   ├── engines/       # base.py (CloneEngine), registry.py, xtts_v2.py
│   └── jobs/          # background processing + SSE event bus
├── docker/            # Dockerfile.cpu, Dockerfile.gpu, docker-compose.yml
├── scripts/           # download_models.py
├── tests/
├── data/              # git-ignored: db.sqlite, voices/{id}/{samples,artifacts}
└── models/            # git-ignored: downloaded model checkpoints
```
