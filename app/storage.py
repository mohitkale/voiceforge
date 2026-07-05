"""On-disk layout + safe audio ingestion.

Every path is derived from server-generated UUIDs — user-supplied filenames
are stored only as metadata (`original_filename`) and never used to build a
filesystem path, which rules out path-traversal via crafted upload names.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from app.config import get_settings

# Real audio-content sniffing (via libsndfile through `soundfile`) rather
# than trusting the client's Content-Type header or file extension.
ALLOWED_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".webm"}


class InvalidAudioError(ValueError):
    pass


@dataclass(frozen=True)
class IngestedSample:
    stored_filename: str
    path: Path
    duration_seconds: float
    sample_rate: int


def voice_dir(voice_id: str) -> Path:
    return get_settings().voices_dir / voice_id


def samples_dir(voice_id: str) -> Path:
    return voice_dir(voice_id) / "samples"


def artifacts_dir(voice_id: str) -> Path:
    return voice_dir(voice_id) / "artifacts"


def preview_path(voice_id: str) -> Path:
    return voice_dir(voice_id) / "preview.wav"


def ensure_voice_dirs(voice_id: str) -> None:
    samples_dir(voice_id).mkdir(parents=True, exist_ok=True)
    artifacts_dir(voice_id).mkdir(parents=True, exist_ok=True)


def delete_voice_dir(voice_id: str) -> None:
    import shutil

    d = voice_dir(voice_id)
    if d.exists() and d.is_relative_to(get_settings().voices_dir):
        shutil.rmtree(d, ignore_errors=True)


def _safe_suffix(original_filename: str | None) -> str:
    suffix = Path(original_filename or "").suffix.lower()
    return suffix if suffix in ALLOWED_SUFFIXES else ".bin"


def save_and_validate_sample(
    voice_id: str,
    raw_bytes: bytes,
    original_filename: str | None,
) -> IngestedSample:
    """Persist an uploaded sample under a random filename and verify it is
    genuinely decodable audio within the configured duration bounds.

    Raises InvalidAudioError on anything that doesn't check out; callers
    should translate that into a 4xx response without leaking internals.
    """
    settings = get_settings()
    ensure_voice_dirs(voice_id)

    stored_filename = f"{uuid.uuid4().hex}{_safe_suffix(original_filename)}"
    dest = samples_dir(voice_id) / stored_filename

    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        tmp.write_bytes(raw_bytes)

        try:
            info = sf.info(str(tmp))
        except Exception as exc:  # noqa: BLE001 - normalize any decode failure
            raise InvalidAudioError("File is not readable audio") from exc

        if info.frames <= 0 or info.samplerate <= 0:
            raise InvalidAudioError("Audio file has no samples")

        duration = info.frames / info.samplerate
        if duration < settings.min_sample_seconds:
            raise InvalidAudioError(
                f"Sample too short ({duration:.1f}s) — need at least "
                f"{settings.min_sample_seconds:.0f}s"
            )
        if duration > settings.max_sample_seconds:
            raise InvalidAudioError(
                f"Sample too long ({duration:.1f}s) — max is "
                f"{settings.max_sample_seconds:.0f}s"
            )

        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)

    return IngestedSample(
        stored_filename=stored_filename,
        path=dest,
        duration_seconds=duration,
        sample_rate=info.samplerate,
    )
