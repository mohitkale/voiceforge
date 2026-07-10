from __future__ import annotations

from fastapi import APIRouter, Depends

from app.engine_readiness import is_engine_ready_cached
from app.engines.registry import is_engine_enabled, list_engines
from app.schemas import EngineStatus
from app.security import auth_dependency

router = APIRouter(prefix="/v1/engines", tags=["engines"], dependencies=[Depends(auth_dependency)])


@router.get("", response_model=list[EngineStatus])
async def get_engines() -> list[EngineStatus]:
    return [
        EngineStatus(
            id=e.id,
            label=e.label,
            capabilities=e.capabilities,
            ready=is_engine_ready_cached(e.id),
            configured=is_engine_enabled(e.id),
        )
        for e in list_engines()
    ]
