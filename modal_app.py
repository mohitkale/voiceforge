"""Deploy VoiceForge to Modal GPU.

Usage:
  modal setup                                    # one-time auth
  modal secret create voiceforge-secrets ...     # see docs/deploy-modal.md
  modal deploy modal_app.py                      # persistent HTTPS URL
  modal run modal_app.py::download_models        # pre-download weights

Everything runs in Modal's cloud — your laptop only runs the CLI.
"""

from __future__ import annotations

import subprocess
import sys

import modal

APP_NAME = "voiceforge"
# T4 is the cheapest GPU tier — good for free-credit testing.
GPU = "T4"

# Scale-to-zero by default (no min_containers). Set min_containers=1 for always-warm GPU.

models_vol = modal.Volume.from_name("voiceforge-models", create_if_missing=True)
data_vol = modal.Volume.from_name("voiceforge-data", create_if_missing=True)

# Engines bundled in this Modal image — also used for VOICEFORGE_ENABLED_ENGINES.
MODAL_ENABLED_ENGINES: tuple[str, ...] = (
    "openvoice-v2",
    "f5-tts",
    "xtts-v2",
    "qwen3-tts",
    "chatterbox",
)
MODAL_DOWNLOAD_ENGINES: tuple[str, ...] = MODAL_ENABLED_ENGINES

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libsndfile1", "ffmpeg", "curl", "git", "sox")
    .pip_install(
        "torch==2.8.0",
        "torchaudio==2.8.0",
        index_url="https://download.pytorch.org/whl/cu126",
    )
    .pip_install(
        "fastapi==0.139.0",
        "uvicorn[standard]==0.50.0",
        "python-multipart==0.0.32",
        "sqlmodel==0.0.39",
        "pydantic==2.13.4",
        "pydantic-settings==2.14.2",
        "aiofiles==24.1.0",
        "soundfile==0.14.0",
        "numpy==2.4.6",
        "scipy==1.17.1",
        "python-dotenv==1.2.2",
        "coqui-tts==0.27.5",
        "transformers==4.57.3",
        "f5-tts==1.1.20",
        "qwen-tts==0.1.1",
    )
    .add_local_file(
        "requirements-chatterbox.txt",
        remote_path="/root/requirements-chatterbox.txt",
        copy=True,
    )
    .run_commands(
        "python -m venv /opt/chatterbox-venv",
        "/opt/chatterbox-venv/bin/pip install --upgrade pip",
        "/opt/chatterbox-venv/bin/pip install torch==2.6.0 torchaudio==2.6.0 "
        "--index-url https://download.pytorch.org/whl/cu126",
        "/opt/chatterbox-venv/bin/pip install -r /root/requirements-chatterbox.txt",
    )
    .env(
        {
            "VOICEFORGE_DEVICE": "cuda",
            "VOICEFORGE_DATA_DIR": "/data",
            "VOICEFORGE_MODELS_DIR": "/models",
            "VOICEFORGE_CHATTERBOX_PYTHON": "/opt/chatterbox-venv/bin/python",
            "VOICEFORGE_QWEN3_TTS_MODEL_DIR": "/models/qwen3-tts",
            "VOICEFORGE_MODAL_DATA_VOLUME": "voiceforge-data",
            "VOICEFORGE_ENABLED_ENGINES": ",".join(MODAL_ENABLED_ENGINES),
            "VOICEFORGE_WARMUP_ENGINES": "qwen3-tts,chatterbox",
            "HF_HOME": "/models",
            "COQUI_TOS_AGREED": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    .add_local_dir("app", remote_path="/root/app")
    .add_local_dir("scripts", remote_path="/root/scripts")
)

app = modal.App(APP_NAME)


@app.function(
    image=image,
    gpu=GPU,
    volumes={"/models": models_vol, "/data": data_vol},
    secrets=[modal.Secret.from_name("voiceforge-secrets")],
    timeout=60 * 30,
    scaledown_window=300,
    max_containers=1,  # one GPU container; scale to zero when idle (no min_containers)
)
@modal.concurrent(max_inputs=1)
@modal.asgi_app()
def web():
    sys.path.insert(0, "/root")
    from app.main import app as fastapi_app

    return fastapi_app


@app.function(
    image=image,
    gpu=GPU,
    volumes={"/models": models_vol},
    secrets=[modal.Secret.from_name("voiceforge-secrets")],
    timeout=60 * 60,
)
def download_models(
    engine: str = "openvoice-v2",
) -> None:
    """Pre-download model checkpoints into the persistent models volume.

    Args:
        engine: One engine id (e.g. ``openvoice-v2``), comma-separated list
            (``openvoice-v2,f5-tts``), or ``all`` for every in-process engine
            in the Modal image (not the full VoiceForge registry).
    """
    sys.path.insert(0, "/root")
    if engine.strip() == "all":
        targets = list(MODAL_DOWNLOAD_ENGINES)
    else:
        targets = [e.strip() for e in engine.split(",") if e.strip()]
        unknown = [t for t in targets if t not in MODAL_DOWNLOAD_ENGINES]
        if unknown:
            supported = ", ".join(MODAL_DOWNLOAD_ENGINES)
            raise ValueError(
                f"Engine(s) not in Modal image: {', '.join(unknown)}. "
                f"Supported: {supported}"
            )

    for name in targets:
        print(f"Downloading engine: {name}")
        subprocess.run(  # noqa: S603 - name is validated against a fixed tuple above
            [sys.executable, "scripts/download_models.py", "--engine", name],
            check=True,
            cwd="/root",
        )
    models_vol.commit()
    print(f"Done. Downloaded: {', '.join(targets)}")
