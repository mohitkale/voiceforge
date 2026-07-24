from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class AlignmentSegment(BaseModel):
    text: str
    start_seconds: float
    end_seconds: float


class TranscriptionResult(BaseModel):
    text: str
    language: str | None = None
    timestamps: list[AlignmentSegment] = Field(default_factory=list)


@runtime_checkable
class AudioIntelligenceProvider(Protocol):
    id: str

    def is_ready(self) -> bool: ...

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        timestamps: bool = False,
    ) -> TranscriptionResult: ...

    def align(
        self,
        audio_path: Path,
        *,
        text: str,
        language: str,
    ) -> list[AlignmentSegment]: ...
