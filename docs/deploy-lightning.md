# Deploy VoiceForge on Lightning.ai

Run VoiceForge on a **Lightning GPU Studio** with Docker — closest to “real
server” development. Good for interactive testing, full engine stack (GPU
image + RVC worker), and a public URL via Lightning’s port proxy.

| | Local Mac | Lightning Studio |
|---|-----------|-------------------|
| Role | Browser + git push | Runs Docker GPU container |
| Docker on Mac | Optional | Runs **in the cloud** |
| Persistence | N/A | Studio disk + Docker volumes |

**Related:** [Modal.com](deploy-modal.md) · [Kaggle](deploy-kaggle.md) · [Local Python setup](local-python-setup.md)

---

## How Lightning works

Lightning gives you a **remote GPU machine** (Studio) with a web terminal and
optional Docker. You clone this repo **inside the Studio**, run
`docker compose --profile gpu`, and expose port **8089** through Lightning’s
URL proxy.

It is not SSH-only — most work happens in the Studio terminal or VS Code
extension, but you can SSH if enabled on your plan.

---

## Prerequisites

1. [Lightning.ai account](https://lightning.ai/)
2. A Studio with **GPU** (T4 or better) and **Docker** enabled
3. Free credits or paid GPU time

---

## Step 1 — Create a GPU Studio

1. Lightning → **Studios** → **New Studio**
2. Choose a **GPU** machine (T4 minimum for RVC; T4 fine for zero-shot engines)
3. Enable **Docker** if offered (or use native Python — Docker path recommended
   for parity with this repo)
4. Wait for Studio to start

Do **not** upload your local `data/` folder — it may contain personal voice
samples.

---

## Step 2 — Clone the repo

In the Studio terminal:

```bash
git clone https://github.com/mohitkale/audio-cloning.git
cd audio-cloning
cp .env.example .env
```

---

## Step 3 — Configure environment

Edit `.env` in the Studio:

```bash
# Required when the Studio URL is reachable from the internet:
VOICEFORGE_API_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# GPU
VOICEFORGE_DEVICE=cuda

# If Reel Studio browser calls VoiceForge directly:
VOICEFORGE_CORS_ORIGINS=http://localhost:3000

# Coqui XTTS license acceptance (non-interactive download)
COQUI_TOS_AGREED=1
```

Save the token — you need the same value in Reel Studio.

---

## Step 4 — Start the GPU stack

```bash
docker compose -f docker/docker-compose.yml --profile gpu up --build -d
```

First build can take **20–40 minutes** (torch, coqui-tts, RVC worker venv).

Check logs:

```bash
docker compose -f docker/docker-compose.yml --profile gpu logs -f voiceforge-gpu
```

Health:

```bash
curl -s http://localhost:8089/healthz
```

---

## Step 5 — Pre-download models (recommended)

```bash
docker compose -f docker/docker-compose.yml --profile gpu run --rm voiceforge-download
```

Or specific engines (run once per engine, or use `--engine all`):

```bash
docker compose -f docker/docker-compose.yml --profile gpu run --rm voiceforge-download \
  -- --engine openvoice-v2
docker compose -f docker/docker-compose.yml --profile gpu run --rm voiceforge-download \
  -- --engine f5-tts
```

Models go to the `models-cache` Docker volume.

---

## Step 6 — Expose port 8089 (public URL)

Lightning Studio UI:

1. Open **Ports** / **App port** / **Connect** (wording varies by Lightning version)
2. Add port **8089**
3. Copy the generated **public HTTPS URL**

Test from your Mac browser:

| URL | Purpose |
|-----|---------|
| `https://<lightning-proxy>/` | VoiceForge Studio |
| `https://<lightning-proxy>/docs` | OpenAPI |
| `https://<lightning-proxy>/healthz` | Health |

Paste **API token** in Studio UI before cloning.

---

## Step 7 — Test clone + synth

In Studio UI:

1. Engine **`openvoice-v2`** first
2. **Record voice** or upload WAV
3. Clone → wait → Synthesize

Or from the Studio terminal:

```bash
python3 scripts/e2e_smoke_test.py --base-url http://localhost:8089 --engine openvoice-v2
```

---

## Step 8 — Connect Reel Studio

On your Mac, in **reel-studio** `.env.local`:

```bash
VOICEFORGE_SERVICE_URL=https://<lightning-public-url-for-8089>
VOICEFORGE_API_TOKEN=<same-as-lightning-.env>
```

Restart Reel Studio dev server. If CORS fails, add your origin to
`VOICEFORGE_CORS_ORIGINS` in Lightning `.env` and restart the container:

```bash
docker compose -f docker/docker-compose.yml --profile gpu up -d --force-recreate
```

---

## Engine choice on Lightning GPU

| Goal | Engine | Tier |
|------|--------|------|
| Fastest / lightest | `openvoice-v2` | `instant` |
| Quality zero-shot | `f5-tts` | `instant` |
| Multilingual | `xtts-v2` | `instant` (CPML) |
| Highest fidelity | `rvc` | `high_fidelity` |
| Extra engines | `qwen3-tts`, `chatterbox` | Extend GPU Dockerfile / workers |

The default `Dockerfile.gpu` includes **RVC worker** at `/opt/rvc-venv`.
Chatterbox / CosyVoice / IndexTTS need extra venv steps (see README engine
table).

---

## Persistence between sessions

| Data | Location | Survives Studio stop? |
|------|----------|------------------------|
| Model weights | Docker volume `models-cache` | Yes, if volume kept |
| Cloned voices | `./data/` bind mount | Yes, if Studio disk kept |
| SQLite DB | `./data/db.sqlite` | Same |

When the Studio is **deleted**, assume all data is lost unless you backed up
`data/` and exported the volume.

---

## Stop / restart

```bash
# Stop containers (Studio keeps disk)
docker compose -f docker/docker-compose.yml --profile gpu stop

# Start again
docker compose -f docker/docker-compose.yml --profile gpu up -d

# Full teardown (keeps volumes)
docker compose -f docker/docker-compose.yml --profile gpu down
```

---

## Troubleshooting log

| Symptom | Cause | Fix |
|---------|-------|-----|
| `docker: command not found` | Docker not enabled in Studio | Enable Docker or use Modal instead |
| NVIDIA runtime error | Wrong Studio type | Pick GPU Studio with NVIDIA |
| Build fails on RVC worker | Network/git clone | Retry; check `requirements-rvc.txt` |
| Port 8089 not reachable externally | Port not published in Lightning UI | Add port in **Ports** panel |
| `503 Engine not ready` | Models missing | Run `voiceforge-download` |
| `401` from Reel Studio | Token mismatch | Sync `VOICEFORGE_API_TOKEN` |
| Slow first clone | Model download | Pre-download step 5 |
| OOM | 12 GB limit in compose | Use lighter engine; reduce concurrent jobs |
| Studio shut down | Idle timeout | Restart Studio; data may persist on disk |

### Platform-specific notes (changelog)

| Date | Note |
|------|------|
| 2026-07 | Default path: `docker compose --profile gpu`. GPU Dockerfile includes RVC isolated worker. Mac users develop on CPU Docker locally; Lightning for GPU. |

---

## Lightning vs Modal

| | Lightning | Modal |
|---|-----------|-------|
| Setup | Docker compose (familiar) | `modal deploy modal_app.py` |
| Full GPU Dockerfile | Yes | Custom `modal_app.py` image |
| RVC / worker venvs | Supported in Dockerfile.gpu | Manual image extension |
| Idle cost | Studio may sleep; check plan | Scales to zero |
| Best for | Full stack testing | Quick public URL |

---

## Related README sections

- [Quickstart (Docker)](../README.md#quickstart-docker)
- [Reel Studio integration](../README.md#integrating-with-reel-studio-or-any-custom-app)
- [Environment variables](../README.md#configuration)
