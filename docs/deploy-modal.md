# Deploy VoiceForge on Modal.com

Run VoiceForge on Modal’s **serverless GPU** with a public HTTPS URL. Your
laptop only installs the Modal CLI — **no local Docker, no GPU, no model
inference on your Mac**.

| | Local Mac | Modal cloud |
|---|-----------|-------------|
| Role | `modal deploy` only | Runs FastAPI + GPU + models |
| Docker | Not required | Not used |
| Cost | Free | GPU seconds + storage (see [Billing](#billing--free-credit-tips)) |

**Best for:** public URL for VoiceForge Studio, Reel Studio integration, shareable demo.

**Related:** [Local Python setup](local-python-setup.md) · [Lightning.ai](deploy-lightning.md) · [Kaggle](deploy-kaggle.md)

---

## How Modal works (not SSH)

Modal is **not** a VPS you SSH into. You:

1. Write `modal_app.py` in this repo (already included).
2. Run `modal deploy modal_app.py` from your Mac.
3. Modal builds a container image **in their cloud**, runs your FastAPI app on a GPU, and gives you a URL like `https://your-workspace--voiceforge-web.modal.run`.

When idle, containers **scale to zero** (default). You are not paying for an always-on server unless you set `min_containers=1` in `modal_app.py`.

---

## Quick start (new Modal account)

```bash
cd /path/to/audio-cloning
python3.12 -m venv .venv && source .venv/bin/activate
pip install 'cbor2>=5.9.0' modal
modal setup

# One-time secret (save the token — Studio needs it)
TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "Save this token: $TOKEN"
modal secret create voiceforge-secrets \
  VOICEFORGE_API_TOKEN="$TOKEN" \
  VOICEFORGE_CORS_ORIGINS="http://localhost:3000"

modal deploy modal_app.py
modal run modal_app.py::download_models --engine all
```

Open `https://<your-workspace>--voiceforge-web.modal.run`, paste the token, clone with **Qwen3-TTS** (recommended), synthesize.

---

## Prerequisites

1. [Modal account](https://modal.com/signup)
2. Working `python3` on your Mac — see [local-python-setup.md](local-python-setup.md)
3. This repo cloned locally

---

## Step 1 — Install Modal CLI (local only)

**Do not** run `pip install modal` on Homebrew system Python — you will get
`externally-managed-environment` (PEP 668). Use the project venv:

```bash
cd /path/to/audio-cloning
python3.12 -m venv .venv          # skip if .venv already exists
source .venv/bin/activate
python -m pip install -U pip
pip install 'cbor2>=5.9.0'        # secure wheel; avoids Rust build on macOS
pip install modal
modal setup
```

See [local-python-setup.md](local-python-setup.md) for PATH fixes, pipx
alternative, and `pip-audit` security checks.

Verify:

```bash
modal profile current
```

---

## Step 2 — Create secrets

VoiceForge requires a bearer token on public endpoints.

Generate a token:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Option A — CLI**

```bash
modal secret create voiceforge-secrets \
  VOICEFORGE_API_TOKEN="paste-token-here" \
  VOICEFORGE_CORS_ORIGINS="http://localhost:3000"
```

**Option B — Modal dashboard**

1. Go to [modal.com](https://modal.com) → **Secrets**
2. **Create secret** → name: `voiceforge-secrets`
3. Keys:
   - `VOICEFORGE_API_TOKEN` = your token
   - `VOICEFORGE_CORS_ORIGINS` = `http://localhost:3000` (add Reel Studio prod URL later)

---

## Step 3 — Deploy

```bash
cd /path/to/audio-cloning
modal deploy modal_app.py
```

First deploy takes **5–20 minutes** (image build in Modal’s cloud). Output:

```text
✓ Created web => https://your-workspace--voiceforge-web.modal.run
```

Bookmark that URL — it is your **VoiceForge Studio + API**.

### Dashboard after deploy

| Modal UI | Purpose |
|----------|---------|
| **Apps** → `voiceforge` | Live URL, container status |
| **Logs** | Clone/synth errors |
| **Secrets** | Edit token / CORS |
| **Volumes** | `voiceforge-models`, `voiceforge-data` |
| **Billing** | Credit usage |

There is no separate “create server” wizard — deployment is **CLI-first**, then manage in the dashboard.

---

## Step 4 — Pre-download models (strongly recommended)

Avoid burning GPU time downloading weights during your first clone:

```bash
modal run modal_app.py::download_models --engine all
```

This downloads every engine **bundled in the Modal image**:

`openvoice-v2`, `f5-tts`, `xtts-v2`, `qwen3-tts`, `chatterbox`

Or pick one:

```bash
modal run modal_app.py::download_models --engine qwen3-tts
modal run modal_app.py::download_models --engine openvoice-v2,f5-tts
```

Note: `scripts/download_models.py` accepts `--engine` (singular). On Modal,
`--engine all` means engines in `MODAL_DOWNLOAD_ENGINES` in `modal_app.py`,
not the full nine-engine registry (RVC, Fish Speech, CosyVoice, IndexTTS are
not in the default Modal image).

Watch logs:

```bash
modal app logs voiceforge
```

---

## Step 5 — Test Studio UI

| URL | Purpose |
|-----|---------|
| `https://<your-url>/` | VoiceForge Studio |
| `https://<your-url>/docs` | OpenAPI |
| `https://<your-url>/healthz` | Health (no token needed) |

### Paste your API token first

Modal injects `VOICEFORGE_API_TOKEN` from the `voiceforge-secrets` secret.
The Studio UI **will look empty** (no engines, no voices) until you paste that
same token into the **API token** field at the top.

Then in Studio:

1. Paste **API token** → all nine engines appear (five **ready** on default Modal)
2. Pick **`qwen3-tts`** (recommended — best clone quality in testing)
3. Record or upload reference (10–15 s, quiet room, read the script)
4. **Clone voice** → wait for status **ready**
5. **Synthesize** → play audio

```bash
export URL="https://your-workspace--voiceforge-web.modal.run"
export TOKEN="your-token"
curl -s "$URL/healthz"
curl -s -H "Authorization: Bearer $TOKEN" "$URL/v1/engines" | python3 -m json.tool
```

---

## Engines on Modal

### Bundled today (`MODAL_ENABLED_ENGINES` in `modal_app.py`)

| Engine | In Modal image | Clone quality (testing notes) | Speed |
|--------|----------------|-------------------------------|-------|
| **`qwen3-tts`** | Yes | **Best** — nearest to real voice | Fast after warm container |
| `chatterbox` | Yes (isolated venv) | Good; slower than Qwen | Slow first synth; daemon keeps model loaded |
| `f5-tts` | Yes | Good for English/Chinese; needs clear ref + ASR | Medium |
| `openvoice-v2` | Yes | Often robotic (two-stage VC) | Medium |
| `xtts-v2` | Yes | Often robotic; CPML non-commercial | Medium |

### Not bundled (show as *not in this deployment* in Studio)

| Engine | What you need |
|--------|----------------|
| `rvc` | GPU Docker + `/opt/rvc-venv` worker |
| `fish-speech` | Self-hosted Fish Speech HTTP sidecar + `VOICEFORGE_FISH_SPEECH_URL` |
| `cosyvoice-3` | Worker venv + `VOICEFORGE_COSYVOICE_PYTHON` |
| `indextts-2` | Worker venv + `VOICEFORGE_INDEXTTS_PYTHON` |

The Studio UI **lists all nine engines** so you can see the full supported set.
Only engines in `MODAL_ENABLED_ENGINES` show **ready** and accept new clones.

To add more engines on a future Modal account, extend `modal_app.py` (image
build + worker venvs) and add ids to `MODAL_ENABLED_ENGINES`.

---

## Configuration reference

Set in `modal_app.py` `.env(...)` block or via `.env` for Docker/local.

| Variable | Default on Modal | Purpose |
|----------|------------------|---------|
| `VOICEFORGE_DEVICE` | `cuda` | Inference device |
| `VOICEFORGE_DATA_DIR` | `/data` | SQLite + voice samples (persistent volume) |
| `VOICEFORGE_MODELS_DIR` | `/models` | HF cache (persistent volume) |
| `HF_HOME` | `/models` | Hugging Face download cache |
| `VOICEFORGE_ENABLED_ENGINES` | five ids (see `MODAL_ENABLED_ENGINES`) | Which engines accept clone/synth |
| `VOICEFORGE_WARMUP_ENGINES` | `qwen3-tts,chatterbox` | Preload models at container start |
| `VOICEFORGE_CHATTERBOX_PYTHON` | `/opt/chatterbox-venv/bin/python` | Isolated Chatterbox worker |
| `VOICEFORGE_MODAL_DATA_VOLUME` | `voiceforge-data` | Auto-commit volume after voice writes |
| `VOICEFORGE_API_TOKEN` | from secret | Bearer auth on `/v1/*` |
| `COQUI_TOS_AGREED` | `1` | Required for XTTS-v2 download |

Edit `MODAL_ENABLED_ENGINES` at the top of `modal_app.py` before deploy to
change which engines are active. Leave `VOICEFORGE_WARMUP_ENGINES` empty to
shorten cold-start time (first synth loads models on demand instead).

### Scaling / cold start (personal testing)

Default `modal_app.py` settings for **low credit usage**:

- **`max_containers=1`** — avoids Modal spinning up many GPU containers for parallel page loads
- **No `min_containers`** — scale to zero when idle (accept 30–90 s cold start)
- **`scaledown_window=300`** — container stays up 5 min after last request

For production / demos, add `min_containers=1` to keep one warm GPU (~continuous billing).

---

## Performance expectations

| Request | Cold container (first visit) | Warm container (same session) |
|---------|------------------------------|-------------------------------|
| `/healthz` | 30–60 s (GPU boot) | &lt; 1 s |
| `/v1/engines` | similar | &lt; 1 s |
| Qwen3 synth (3 s audio) | 60–90 s | **5–15 s** |
| Chatterbox synth | 60–120 s | **10–30 s** |

Cold starts are normal for personal/testing usage with scale-to-zero.

---

## Step 6 — Connect Reel Studio

In **reel-studio** `.env.local`:

```bash
VOICEFORGE_SERVICE_URL=https://your-workspace--voiceforge-web.modal.run
VOICEFORGE_API_TOKEN=your-same-token
```

Restart Reel Studio. Clone/synth traffic goes to Modal, not localhost.

If the browser hits CORS errors, add your origin to the Modal secret and redeploy:

```bash
modal secret create voiceforge-secrets \
  VOICEFORGE_API_TOKEN="..." \
  VOICEFORGE_CORS_ORIGINS="http://localhost:3000,https://your-app.vercel.app"
modal deploy modal_app.py
```

---

## Dev vs production URL

| Command | URL lifetime | Use |
|---------|--------------|-----|
| `modal serve modal_app.py` | Until terminal stops | Local iteration |
| `modal deploy modal_app.py` | Persistent | Reel Studio / sharing |

Use **`modal deploy`** for integration.

---

## Billing / free-credit tips

- GPU time (T4) is billed per second **while a container runs**.
- Cold starts + model load count toward usage.
- Pre-download models once (`download_models --engine all`) — weights persist in `voiceforge-models` volume.
- **Start with `qwen3-tts`** — best quality and fastest in-process engine.
- Scale-to-zero (default) saves credits between test sessions.
- Avoid leaving `min_containers=1` on unless you need instant responses.

Stop spending:

```bash
modal app stop voiceforge   # remove deployed app
```

Volumes retain model cache and cloned voices for the next deploy on the same account.

---

## Troubleshooting log

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Secret voiceforge-secrets not found` | Secret not created | Step 2 |
| `python` / `modal` not found | PATH broken | [local-python-setup.md](local-python-setup.md) |
| Image build fails on deps | Pin conflict | See `modal_app.py` pins; Chatterbox uses isolated venv |
| `503 Engine not ready` | Models not downloaded | `modal run modal_app.py::download_models --engine all` |
| `401 Missing bearer token` | Token missing in UI/curl | Paste token from Modal secret into Studio |
| Studio empty / no engines | Token not set in UI | Paste `VOICEFORGE_API_TOKEN` value |
| Voice created then **404** | Data volume not committed | Fixed — redeploy latest; voices persist in `voiceforge-data` |
| OpenVoice/XTTS sounds **robotic** | Two-stage VC quality | Use **Qwen3-TTS** or Chatterbox instead |
| F5 clone fails / OOM | Whisper + F5 both on GPU | Fixed — ASR runs on CPU before F5 loads |
| Chatterbox 502: `PYTHONHASHSEED` | Modal invalid env in worker subprocess | Fixed — worker uses `env PYTHONHASHSEED=0` |
| Chatterbox synth very slow | Model reload per request | Fixed — long-lived Chatterbox daemon |
| Slow first request (60s+) | Cold start + warmup | Expected with scale-to-zero; wait or set `min_containers=1` |
| Many Modal containers (7+) | Autoscale per queued request | `max_containers=1` in `modal_app.py` |
| Synthesis 502: tensors on different device | Coqui GPU bug | Redeploy; clone a fresh voice |
| `download_models` fails on RVC | Engine not in Modal image | Use `--engine all` (Modal subset only) |
| CORS from Reel Studio | Origin not allowed | Update `VOICEFORGE_CORS_ORIGINS` secret |
| Out of credits | Free tier exhausted | New Modal account; volumes do not transfer |

---

## Session changelog (2026-07)

What was validated on Modal during initial deployment:

| Topic | Outcome |
|-------|---------|
| **Best clone quality** | **Qwen3-TTS** — nearest to real voice in testing |
| **Chatterbox** | Works after PYTHONHASHSEED + daemon fixes; slower than Qwen |
| **OpenVoice / XTTS** | Functional but often robotic-sounding |
| **F5-TTS** | English/Chinese; needs clear reference + auto-transcript |
| **Fish / Cosy / Index / RVC** | Not in default Modal image — use GPU Docker or extend image |
| **Studio UI** | In-browser recording, Indianized read-aloud scripts, token auth |
| **Volumes** | `voiceforge-models` (weights), `voiceforge-data` (voices + SQLite) |

---

## Files in this repo

| File | Purpose |
|------|---------|
| `modal_app.py` | Modal app — image, GPU, volumes, enabled engines |
| `docs/deploy-modal.md` | This guide |
| `app/engines/chatterbox_daemon.py` | Long-lived Chatterbox worker (model stays loaded) |
| `app/engines/subprocess_env.py` | Safe worker subprocess env (PYTHONHASHSEED) |
| `app/engine_readiness.py` | Cached readiness + startup warmup |
| `app/persistence.py` | Modal data volume commit after writes |
| `app/`, `scripts/` | Mounted into Modal container at deploy time |

---

## Uninstall / cleanup

```bash
modal app stop voiceforge
modal volume delete voiceforge-models   # only if you want to wipe model cache
modal volume delete voiceforge-data     # wipes cloned voices
modal secret delete voiceforge-secrets
```

---

## Next account: remaining engines

When you set up a fresh Modal account to test Fish Speech, CosyVoice 3,
IndexTTS2, or RVC:

1. Create new Modal account + `modal setup`
2. Recreate `voiceforge-secrets` with a new token
3. `modal deploy modal_app.py`
4. `modal run modal_app.py::download_models --engine all` (re-download weights into new account’s volume)
5. Extend `modal_app.py` image with worker venvs (see `docker/Dockerfile.gpu` and `requirements-*.txt`)
6. Add engine ids to `MODAL_ENABLED_ENGINES`
7. Or use [Lightning.ai / GPU Docker](deploy-lightning.md) for full worker stack without Modal image surgery
