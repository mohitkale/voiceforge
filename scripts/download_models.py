#!/usr/bin/env python3
"""Pre-download engine model checkpoints so the first API request isn't slow
(and so `docker compose up` + a cold first request don't race against a
multi-GB download under load).

Usage (inside the container or a matching local venv):
    python scripts/download_models.py [--engine xtts-v2]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402
from app.providers.registry import (  # noqa: E402
    CHATTERBOX_REVISION,
    QWEN3_ALIGNER_REVISION,
    QWEN3_ASR_REVISION,
    QWEN3_TTS_REVISION,
    VOXCPM2_REVISION,
    list_provider_manifests,
)


def download_xtts_v2() -> None:
    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TTS_HOME", str(settings.models_dir))
    os.environ.setdefault("COQUI_TOS_AGREED", "1")

    print("Downloading XTTS-v2 (Coqui, CPML license — non-commercial/research use)...")
    from TTS.api import TTS

    TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    print(f"Done. Cached under {settings.models_dir}")


def download_f5_tts() -> None:
    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(settings.models_dir))

    print("Downloading F5-TTS v1 base (CC-BY-NC pretrained weights)...")
    from f5_tts.api import F5TTS

    F5TTS(model="F5TTS_v1_Base", hf_cache_dir=str(settings.models_dir))
    print(f"Done. Cached under {settings.models_dir}")


def download_openvoice_v2() -> None:
    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TTS_HOME", str(settings.models_dir))

    print("Downloading OpenVoice V2 VC + separately licensed YourTTS base...")
    from TTS.api import TTS

    TTS("voice_conversion_models/multilingual/multi-dataset/openvoice_v2")
    TTS("tts_models/multilingual/multi-dataset/your_tts")
    print(f"Done. Cached under {settings.models_dir}")


def download_rvc() -> None:
    """Pre-fetch RVC base weights (HuBERT, RMVPE) via the isolated worker."""
    import subprocess

    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)

    rvc_python = settings.rvc_python
    if rvc_python is None:
        default = Path("/opt/rvc-venv/bin/python")
        rvc_python = default if default.is_file() else None

    worker = Path(__file__).resolve().parent / "rvc_worker.py"
    if rvc_python is None or not worker.is_file():
        print(
            "Skipping RVC download — set VOICEFORGE_RVC_PYTHON or install "
            "/opt/rvc-venv (see requirements-rvc.txt)"
        )
        return

    print("Downloading RVC base models (HuBERT, RMVPE) via worker setup...")
    subprocess.run(  # noqa: S603 — trusted paths from config / /opt/rvc-venv
        [str(rvc_python), str(worker), "setup"],
        check=True,
    )
    print(f"Done. RVC assets cached via worker under {settings.models_dir}")


def download_chatterbox() -> None:
    import subprocess

    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)

    python = settings.chatterbox_python
    if python is None:
        default = Path("/opt/chatterbox-venv/bin/python")
        python = default if default.is_file() else None
    worker = Path(__file__).resolve().parent / "chatterbox_worker.py"
    if python is None or not worker.is_file():
        print(
            "Skipping Chatterbox download — set VOICEFORGE_CHATTERBOX_PYTHON "
            "(see requirements-chatterbox.txt / /opt/chatterbox-venv)"
        )
        return

    model_dir = settings.chatterbox_model_dir or settings.models_dir / "chatterbox"
    print(f"Downloading Chatterbox Multilingual V3 at {CHATTERBOX_REVISION}...")
    subprocess.run(  # noqa: S603
        [
            str(python),
            str(worker),
            "setup",
            "--model-dir",
            str(model_dir),
            "--revision",
            CHATTERBOX_REVISION,
        ],
        check=True,
    )
    print(f"Done. Cached under {model_dir}")


def download_qwen3_tts() -> None:
    """Download only; do not import or instantiate the model implementation."""

    from huggingface_hub import snapshot_download

    settings = get_settings()
    model_dir = settings.qwen3_tts_model_dir or settings.models_dir / "qwen3-tts"
    print(f"Downloading Qwen3-TTS 1.7B Base at {QWEN3_TTS_REVISION}...")
    snapshot_download(
        repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        revision=QWEN3_TTS_REVISION,
        local_dir=str(model_dir),
    )
    print(f"Done. Cached under {model_dir}")


def download_qwen3_asr() -> None:
    """Explicit opt-in snapshots only; application startup never calls this."""

    from huggingface_hub import snapshot_download

    settings = get_settings()
    asr_dir = settings.qwen3_asr_model_dir or settings.models_dir / "qwen3-asr-0.6b"
    aligner_dir = (
        settings.qwen3_aligner_model_dir or settings.models_dir / "qwen3-forced-aligner-0.6b"
    )
    print(f"Downloading Qwen3-ASR 0.6B at {QWEN3_ASR_REVISION}...")
    snapshot_download(
        repo_id="Qwen/Qwen3-ASR-0.6B",
        revision=QWEN3_ASR_REVISION,
        local_dir=str(asr_dir),
    )
    print(f"Downloading Qwen3 Forced Aligner at {QWEN3_ALIGNER_REVISION}...")
    snapshot_download(
        repo_id="Qwen/Qwen3-ForcedAligner-0.6B",
        revision=QWEN3_ALIGNER_REVISION,
        local_dir=str(aligner_dir),
    )
    print(f"Done. ASR={asr_dir} aligner={aligner_dir}")


def download_voxcpm2() -> None:
    """Explicit opt-in snapshot; no provider code is imported."""

    from huggingface_hub import snapshot_download

    settings = get_settings()
    model_dir = settings.voxcpm2_model_dir or settings.models_dir / "voxcpm2"
    print(f"Downloading VoxCPM2 at {VOXCPM2_REVISION}...")
    snapshot_download(
        repo_id="openbmb/VoxCPM2",
        revision=VOXCPM2_REVISION,
        local_dir=str(model_dir),
    )
    print(f"Done. Cached under {model_dir}")


def download_fish_speech() -> None:
    print(
        "Fish Speech uses a self-hosted sidecar — no weights are downloaded "
        "into the VoiceForge process. Start fish-speech locally and set "
        "VOICEFORGE_FISH_SPEECH_URL (see requirements-fish.txt)."
    )


def download_cosyvoice_3() -> None:
    import subprocess

    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)

    python = settings.cosyvoice_python
    if python is None:
        default = Path("/opt/cosyvoice-venv/bin/python")
        python = default if default.is_file() else None
    worker = Path(__file__).resolve().parent / "cosyvoice_worker.py"
    if python is None or not worker.is_file():
        print(
            "Skipping CosyVoice download — set VOICEFORGE_COSYVOICE_PYTHON "
            "(see requirements-cosyvoice.txt)"
        )
        return

    print("Downloading Fun-CosyVoice3-0.5B via worker setup...")
    subprocess.run(  # noqa: S603
        [str(python), str(worker), "setup", "--models-dir", str(settings.models_dir)],
        check=True,
    )
    print(f"Done. Cached under {settings.models_dir}")


def download_indextts_2() -> None:
    import subprocess

    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)

    python = settings.indextts_python
    if python is None:
        default = Path("/opt/indextts-venv/bin/python")
        python = default if default.is_file() else None
    worker = Path(__file__).resolve().parent / "indextts_worker.py"
    if python is None or not worker.is_file():
        print(
            "Skipping IndexTTS2 download — set VOICEFORGE_INDEXTTS_PYTHON "
            "(see requirements-indextts.txt)"
        )
        return

    print("Downloading IndexTTS-2 via worker setup...")
    subprocess.run(  # noqa: S603
        [str(python), str(worker), "setup", "--models-dir", str(settings.models_dir)],
        check=True,
    )
    print(f"Done. Cached under {settings.models_dir}")


ENGINES = {
    "xtts-v2": download_xtts_v2,
    "f5-tts": download_f5_tts,
    "openvoice-v2": download_openvoice_v2,
    "rvc": download_rvc,
    "chatterbox": download_chatterbox,
    "qwen3-tts": download_qwen3_tts,
    "fish-speech": download_fish_speech,
    "cosyvoice-3": download_cosyvoice_3,
    "indextts-2": download_indextts_2,
    "qwen3-asr": download_qwen3_asr,
    "voxcpm2": download_voxcpm2,
}

# "all" preserves the established engine set. Experimental providers require
# an explicit --engine selection so a routine setup cannot pull new multi-GB
# snapshots unexpectedly.
DEFAULT_ENGINES = [
    "xtts-v2",
    "f5-tts",
    "openvoice-v2",
    "rvc",
    "chatterbox",
    "qwen3-tts",
    "fish-speech",
    "cosyvoice-3",
    "indextts-2",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="List providers and immutable revisions without downloading anything",
    )
    parser.add_argument(
        "--engine",
        choices=[*ENGINES.keys(), "all"],
        default="all",
        help="Which engine's model(s) to download (default: all)",
    )
    args = parser.parse_args()

    if args.list:
        for manifest in list_provider_manifests():
            revisions = ", ".join(
                f"{model.model_id}@{model.revision or 'UNPINNED'}"
                for model in manifest.models
            )
            print(
                f"{manifest.id}: {manifest.integration}; "
                f"{revisions or 'no manifest model'}"
            )
        return

    targets = DEFAULT_ENGINES if args.engine == "all" else [args.engine]
    for name in targets:
        ENGINES[name]()


if __name__ == "__main__":
    main()
