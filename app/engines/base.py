"""The `CloneEngine` protocol — the one interface the API and jobs layer talk
to. Mirrors Reel Studio's `VoiceProvider` pattern (`src/providers/voice/`):
implement this once per engine, register it, nothing else changes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

Tier = Literal["instant", "high_fidelity"]

# (message, extra_fields) -> None. Engines call this during create_voice to
# push SSE progress events; None means "no progress reporting available".
ProgressFn = Callable[[str, dict | None], Awaitable[None]]


class CloneCapabilities(BaseModel):
    zero_shot: bool
    fine_tunable: bool
    min_sample_seconds: float
    recommended_sample_seconds: float
    languages: list[str]
    requires_gpu: bool
    license: str
    approx_vram_gb: float | None = None


class SynthesizeOptions(BaseModel):
    sample_rate: int | None = None
    speed: float | None = None
    language: str | None = None


class VoiceArtifact(BaseModel):
    """What `create_voice` produces and what gets stored as `Voice.artifact`
    (JSON) in the DB. `data` is intentionally opaque/engine-specific — e.g.
    XTTS-v2 stores relative paths to cached conditioning-latent tensors."""

    engine_id: str
    tier: Tier
    data: dict = {}


class EngineError(RuntimeError):
    """Expected, user-facing engine failure (bad audio, engine not ready,
    unsupported language, ...) — distinct from unexpected bugs so the API can
    surface a clean 4xx instead of a generic 500."""


@runtime_checkable
class CloneEngine(Protocol):
    id: str
    label: str
    capabilities: CloneCapabilities

    def is_ready(self) -> bool:
        """Model weights downloaded/loaded and usable right now."""
        ...

    async def create_voice(
        self,
        voice_id: str,
        sample_paths: list[Path],
        tier: Tier,
        language: str,
        on_progress: ProgressFn | None = None,
    ) -> VoiceArtifact:
        """Instant tier: extract + cache a speaker embedding/conditioning
        latent from the reference sample(s). High-fidelity tier: same for
        now (re-conditions on the longer/cleaner sample) until a dedicated
        fine-tuning engine (e.g. RVC) lands behind this same interface."""
        ...

    async def synthesize(
        self,
        voice_id: str,
        artifact: VoiceArtifact,
        text: str,
        opts: SynthesizeOptions,
    ) -> bytes:
        """Return 16-bit PCM WAV bytes."""
        ...
