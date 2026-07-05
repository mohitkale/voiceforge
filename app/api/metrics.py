from __future__ import annotations

from fastapi import APIRouter, Depends

from app.metrics import get_metrics
from app.schemas import MetricsSnapshot
from app.security import auth_dependency

router = APIRouter(prefix="/v1", tags=["metrics"], dependencies=[Depends(auth_dependency)])


@router.get("/metrics", response_model=MetricsSnapshot)
async def service_metrics() -> MetricsSnapshot:
    """In-process counters since startup (voices, synth, errors, uptime)."""
    return MetricsSnapshot(**get_metrics().snapshot())
