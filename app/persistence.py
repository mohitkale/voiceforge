"""Optional persistence hooks for cloud deployments (e.g. Modal volumes)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("voiceforge.persistence")


def commit_data_volume() -> None:
    """Flush the Modal data volume after SQLite / voice file writes."""
    name = os.environ.get("VOICEFORGE_MODAL_DATA_VOLUME", "").strip()
    if not name:
        return
    try:
        import modal

        modal.Volume.from_name(name).commit()
    except Exception:
        logger.warning("Modal data volume commit failed", exc_info=True)
