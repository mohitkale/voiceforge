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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402


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

    print("Downloading F5-TTS v1 base (Apache-2.0 / CC)...")
    from f5_tts.api import F5TTS

    F5TTS(model="F5TTS_v1_Base", hf_cache_dir=str(settings.models_dir))
    print(f"Done. Cached under {settings.models_dir}")


def download_openvoice_v2() -> None:
    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TTS_HOME", str(settings.models_dir))

    print("Downloading OpenVoice V2 VC + YourTTS base (MIT)...")
    from TTS.api import TTS

    TTS("voice_conversion_models/multilingual/multi-dataset/openvoice_v2")
    TTS("tts_models/multilingual/multi-dataset/your_tts")
    print(f"Done. Cached under {settings.models_dir}")


ENGINES = {
    "xtts-v2": download_xtts_v2,
    "f5-tts": download_f5_tts,
    "openvoice-v2": download_openvoice_v2,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine",
        choices=[*ENGINES.keys(), "all"],
        default="all",
        help="Which engine's model(s) to download (default: all)",
    )
    args = parser.parse_args()

    targets = ENGINES.keys() if args.engine == "all" else [args.engine]
    for name in targets:
        ENGINES[name]()


if __name__ == "__main__":
    main()
