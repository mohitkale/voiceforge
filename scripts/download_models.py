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


ENGINES = {
    "xtts-v2": download_xtts_v2,
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
