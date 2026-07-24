from __future__ import annotations

from fastapi import APIRouter, Depends

from app.providers.models import ProviderStatus
from app.providers.registry import provider_statuses
from app.security import auth_dependency

router = APIRouter(
    prefix="/v1/providers",
    tags=["providers"],
    dependencies=[Depends(auth_dependency)],
)


@router.get("", response_model=list[ProviderStatus])
async def get_providers() -> list[ProviderStatus]:
    """List engine and audio-intelligence manifests without loading models."""

    return provider_statuses()
