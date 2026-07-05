"""SQLModel table definitions. SQLite is the only supported backend — this is
a single-user, local-first tool, matching Reel Studio's own DB philosophy.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import JSON, Column, Field, Relationship, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return uuid.uuid4().hex


class VoiceTier(StrEnum):
    instant = "instant"
    high_fidelity = "high_fidelity"


class VoiceStatus(StrEnum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Voice(SQLModel, table=True):
    __tablename__ = "voices"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    engine_id: str = Field(index=True)
    tier: VoiceTier
    status: VoiceStatus = Field(default=VoiceStatus.processing, index=True)
    consent: bool = Field(default=False)
    language: str = Field(default="en")
    error_message: str | None = None

    # Engine-specific artifact metadata (e.g. paths to cached conditioning
    # latents). Opaque to everything except the engine that produced it.
    artifact: dict = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    ready_at: datetime | None = None

    samples: list["VoiceSample"] = Relationship(
        back_populates="voice",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class VoiceSample(SQLModel, table=True):
    __tablename__ = "voice_samples"

    id: str = Field(default_factory=_uuid, primary_key=True)
    voice_id: str = Field(foreign_key="voices.id", index=True)
    # Server-generated filename on disk (never derived from user input).
    stored_filename: str
    original_filename: str | None = None
    duration_seconds: float
    sample_rate: int
    created_at: datetime = Field(default_factory=_now)

    voice: Voice | None = Relationship(back_populates="samples")
