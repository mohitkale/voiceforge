"""Pydantic request/response shapes for the public API.

Field names/shapes are kept close to Reel Studio's own `VoiceSummary` /
`SynthResult` conventions (camelCase over the wire) so its client-side
adapter is a thin mapping, not a translation layer.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db_models import VoiceStatus, VoiceTier
from app.engines.base import CloneCapabilities


def _to_camel(s: str) -> str:
    head, *tail = s.split("_")
    return head + "".join(w.capitalize() for w in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class EngineStatus(CamelModel):
    id: str
    label: str
    capabilities: CloneCapabilities
    ready: bool
    configured: bool


class VoiceSummary(CamelModel):
    id: str
    name: str
    engine_id: str
    tier: VoiceTier
    status: VoiceStatus
    language: str
    created_at: datetime
    preview_url: str | None = None


class VoiceDetail(VoiceSummary):
    error_message: str | None = None
    ready_at: datetime | None = None
    sample_count: int = 0


class SynthesizeRequest(CamelModel):
    voice_id: str
    text: str = Field(min_length=1)
    sample_rate: int | None = None
    speed: float | None = Field(default=None, gt=0.25, le=4.0)
    language: str | None = None


class MetricsSnapshot(CamelModel):
    uptime_seconds: float
    voices_created: int
    voices_ready: int
    voices_failed: int
    synth_requests: int
    synth_errors: int


class HealthResponse(CamelModel):
    status: str
    service: str
    version: str
    engines_ready: int
    engines_total: int
