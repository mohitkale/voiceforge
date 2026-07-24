"""Sanitize environment for isolated engine worker subprocesses.

Modal injects an invalid ``PYTHONHASHSEED`` that child Python interpreters
reject at pre-init. Always force a known-good value.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path


def sanitized_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    # Inference workers receive local paths and must never contact a model hub.
    # Explicit setup/download commands are launched separately without this
    # environment.
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    return env


def worker_exec_command(
    python: Path,
    script: Path,
    args: Sequence[str],
) -> list[str]:
    """Build argv for a worker subprocess with a safe hash seed on Linux."""
    py = str(python)
    scr = str(script)
    if sys.platform != "win32":
        return ["/usr/bin/env", "PYTHONHASHSEED=0", py, scr, *args]
    return [py, scr, *args]
