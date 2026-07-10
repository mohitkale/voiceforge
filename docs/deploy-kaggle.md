# Deploy / test VoiceForge on Kaggle

Kaggle provides **free GPU notebook hours** (~30 h/week on T4/P100). It is
**not** a good platform for a permanent public VoiceForge URL or Reel Studio
integration.

| | Kaggle | Modal / Lightning |
|---|--------|-------------------|
| Public HTTPS URL | No (stable) | Yes |
| Reel Studio integration | No | Yes |
| Best use | Engine smoke tests, dev experiments | Hosted service |

**Related:** [Modal.com](deploy-modal.md) · [Lightning.ai](deploy-lightning.md) · [Local Python setup](local-python-setup.md)

---

## What Kaggle is good for

- Confirm GPU engines work (`openvoice-v2`, `f5-tts`, `xtts-v2`)
- Try clone/synth without local Docker
- Learn the API before deploying to Modal/Lightning

## What Kaggle is not good for

- 24/7 hosted VoiceForge Studio URL
- Connecting Reel Studio (no stable endpoint)
- Production demos (sessions expire; networking is restricted)

For a shareable URL, use [deploy-modal.md](deploy-modal.md) or [deploy-lightning.md](deploy-lightning.md).

---

## Prerequisites

1. [Kaggle account](https://www.kaggle.com/)
2. Phone verification enabled (required for GPU)
3. Optional: upload this repo as a Kaggle Dataset, or clone from GitHub in-notebook

---

## Step 1 — Create a GPU notebook

1. Kaggle → **Code** → **New Notebook**
2. **Settings** (right panel):
   - **Accelerator** → **GPU T4 x2** (or P100 if T4 unavailable)
   - **Internet** → **On** (required for pip + Hugging Face downloads)
   - **Persistence** → optional; session still time-limited

---

## Step 2 — Clone the repo

First code cell:

```python
!git clone https://github.com/mohitkale/audio-cloning.git
%cd audio-cloning
```

Replace the URL with your fork if needed.

---

## Step 3 — Install dependencies

```python
import sys
!{sys.executable} -m pip install -q --upgrade pip

# PyTorch CUDA (match Kaggle CUDA version — cu121 is typical)
!{sys.executable} -m pip install -q torch==2.8.0 torchaudio==2.8.0 \
    --index-url https://download.pytorch.org/whl/cu121

# VoiceForge core + one engine to start
!{sys.executable} -m pip install -q -r requirements.txt -r requirements-xtts.txt -r requirements-f5.txt

import os
os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["VOICEFORGE_DEVICE"] = "cuda"
os.environ["VOICEFORGE_DATA_DIR"] = "/kaggle/working/data"
os.environ["VOICEFORGE_MODELS_DIR"] = "/kaggle/working/models"
```

**Start minimal** — only add `requirements-qwen3.txt` etc. after OpenVoice works.

---

## Step 4 — Pre-download models (optional)

```python
!{sys.executable} scripts/download_models.py --engine openvoice-v2
```

Models land in `/kaggle/working/models`. Add **Output** in notebook settings
or download before session ends — otherwise they are lost.

---

## Step 5 — Run the API in the notebook

```python
import subprocess
import time
import os

os.environ["VOICEFORGE_DEVICE"] = "cuda"
os.environ["VOICEFORGE_DATA_DIR"] = "/kaggle/working/data"
os.environ["VOICEFORGE_MODELS_DIR"] = "/kaggle/working/models"

proc = subprocess.Popen(
    [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", "8089",
    ],
    cwd="/kaggle/working/audio-cloning",
)
time.sleep(8)
print("Server starting…")
```

---

## Step 6 — Test inside the notebook (no public URL)

Kaggle does **not** expose port 8089 as a stable public URL. Test with
in-notebook HTTP:

```python
import httpx

BASE = "http://127.0.0.1:8089"
r = httpx.get(f"{BASE}/healthz", timeout=30)
print(r.json())

r = httpx.get(f"{BASE}/v1/engines", timeout=60)
for e in r.json():
    print(e["id"], "ready=", e["ready"])
```

### Smoke test via script

```python
!{sys.executable} scripts/e2e_smoke_test.py \
    --base-url http://127.0.0.1:8089 \
    --engine openvoice-v2
```

---

## Step 7 — Studio UI (limited)

Kaggle may show a proxy link for notebook web apps, but it is **unreliable**
for multipart uploads and long-running clones. Prefer API/curl tests on Kaggle;
use Modal/Lightning for the full Studio UI.

---

## Session limits

| Limit | Typical value |
|-------|----------------|
| GPU session length | ~9–12 hours max |
| Weekly GPU quota | ~30 hours |
| Idle timeout | Session stops if idle |
| Disk | `/kaggle/working` — persist via **Save Version** / Output |

Save `data/` and `models/` before shutdown if you want to reuse weights.

---

## Engine recommendations on Kaggle

| Engine | Kaggle | Notes |
|--------|--------|-------|
| `openvoice-v2` | Recommended first | Lightest |
| `f5-tts` | Good | Needs clear reference speech |
| `xtts-v2` | OK | CPML license; slower download |
| `qwen3-tts` | Tight VRAM | May OOM on T4 with other models loaded |
| `chatterbox` | Not recommended | Heavy deps; use Modal instead |
| `rvc` | Hard | Needs isolated worker venv |
| `fish-speech` | No | Needs sidecar container |

---

## Troubleshooting log

| Symptom | Cause | Fix |
|---------|-------|-----|
| GPU not available | Quota exhausted or phone not verified | Wait for weekly reset; verify account |
| `pip install torch` fails | Wrong CUDA index | Try `cu121` or `cu124` per Kaggle CUDA version |
| `Engine not ready` | Models not downloaded | Run `download_models.py` |
| `libtorchcodec` / torchcodec errors | F5/coqui optional deps | Use shared `app/engines/asr.py` path; avoid torchcodec |
| Session died mid-clone | Time limit | Save checkpoints; use Modal for long jobs |
| Cannot open Studio from phone | No public URL | Expected — use Modal/Lightning |
| `git clone` fails private repo | Auth | Use public fork or Kaggle Dataset |
| OOM on GPU | Model too large | `openvoice-v2` only; restart kernel |

### Workarounds tried (changelog)

| Date | Note |
|------|------|
| 2026-07 | Kaggle documented as **dev/smoke-test only**. ngrok/tunneling not recommended (ToS + unstable). Use Modal for Reel Studio URL. |

---

## Next step — real hosting

When Kaggle tests pass:

1. [Deploy on Modal.com](deploy-modal.md) — easiest public URL
2. [Deploy on Lightning.ai](deploy-lightning.md) — full Docker GPU stack

Then set in Reel Studio:

```bash
VOICEFORGE_SERVICE_URL=https://your-hosted-url
VOICEFORGE_API_TOKEN=your-token
```
