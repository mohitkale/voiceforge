from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.db_models import Voice, VoiceSample, VoiceStatus, VoiceTier
from app.engines.registry import UnknownEngineError, get_engine
from app.jobs.voice_jobs import run_create_voice
from app.schemas import VoiceDetail, VoiceSummary
from app.security import auth_dependency
from app.storage import (
    InvalidAudioError,
    delete_voice_dir,
    preview_path,
    samples_dir,
    save_and_validate_sample,
)

logger = logging.getLogger("voiceforge.api.voices")

router = APIRouter(prefix="/v1/voices", tags=["voices"], dependencies=[Depends(auth_dependency)])

# Keep references to background tasks so they aren't garbage-collected mid-flight.
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _to_summary(voice: Voice) -> VoiceSummary:
    has_preview = preview_path(voice.id).exists()
    return VoiceSummary(
        id=voice.id,
        name=voice.name,
        engine_id=voice.engine_id,
        tier=voice.tier,
        status=voice.status,
        language=voice.language,
        created_at=voice.created_at,
        preview_url=f"/v1/voices/{voice.id}/preview" if has_preview else None,
    )


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File '{file.filename}' exceeds the {max_bytes // (1024 * 1024)}MB limit",
        )
    return data


@router.post("", response_model=VoiceDetail, status_code=status.HTTP_201_CREATED)
async def create_voice(
    name: str = Form(..., min_length=1, max_length=200),
    engine_id: str = Form(...),
    tier: VoiceTier = Form(...),
    consent: bool = Form(...),
    language: str = Form("en"),
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
) -> VoiceDetail:
    if not consent:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "consent=true is required — confirm you have the right to clone this voice",
        )

    try:
        clone_engine = get_engine(engine_id)
    except UnknownEngineError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown engine '{engine_id}'") from None

    if not clone_engine.is_ready():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Engine '{engine_id}' is not ready yet"
        )

    if tier == VoiceTier.high_fidelity and not clone_engine.capabilities.fine_tunable:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Engine '{engine_id}' does not support tier='high_fidelity'",
        )
    if tier == VoiceTier.instant and not clone_engine.capabilities.zero_shot:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Engine '{engine_id}' requires tier='high_fidelity' (fine-tuned training)",
        )

    settings = get_settings()
    if not files:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "At least one audio file is required"
        )
    if len(files) > settings.max_samples_per_voice:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Too many files (max {settings.max_samples_per_voice} per voice)",
        )

    voice = Voice(
        name=name,
        engine_id=engine_id,
        tier=tier,
        consent=consent,
        language=language,
        status=VoiceStatus.processing,
    )
    session.add(voice)
    session.commit()
    session.refresh(voice)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    sample_paths: list[str] = []
    try:
        for f in files:
            raw = await _read_upload(f, max_bytes)
            try:
                ingested = save_and_validate_sample(voice.id, raw, f.filename)
            except InvalidAudioError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

            session.add(
                VoiceSample(
                    voice_id=voice.id,
                    stored_filename=ingested.stored_filename,
                    original_filename=f.filename,
                    duration_seconds=ingested.duration_seconds,
                    sample_rate=ingested.sample_rate,
                )
            )
            sample_paths.append(str(ingested.path))
        session.commit()
    except HTTPException:
        session.delete(voice)
        session.commit()
        delete_voice_dir(voice.id)
        raise

    _spawn(run_create_voice(voice.id, sample_paths, language))

    return VoiceDetail(**_to_summary(voice).model_dump(), sample_count=len(sample_paths))


@router.get("", response_model=list[VoiceSummary])
async def list_voices(session: Session = Depends(get_session)) -> list[VoiceSummary]:
    voices = session.exec(select(Voice).order_by(Voice.created_at.desc())).all()
    return [_to_summary(v) for v in voices]


@router.get("/{voice_id}", response_model=VoiceDetail)
async def get_voice(voice_id: str, session: Session = Depends(get_session)) -> VoiceDetail:
    voice = session.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice not found")
    sample_count = len(voice.samples)
    return VoiceDetail(
        **_to_summary(voice).model_dump(),
        error_message=voice.error_message,
        ready_at=voice.ready_at,
        sample_count=sample_count,
    )


@router.delete("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice(voice_id: str, session: Session = Depends(get_session)) -> None:
    voice = session.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice not found")
    session.delete(voice)
    session.commit()
    delete_voice_dir(voice_id)


@router.post("/{voice_id}/samples", response_model=VoiceDetail)
async def add_sample(
    voice_id: str,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
) -> VoiceDetail:
    voice = session.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice not found")

    settings = get_settings()
    existing_count = len(voice.samples)
    if existing_count + len(files) > settings.max_samples_per_voice:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Too many samples (max {settings.max_samples_per_voice} per voice)",
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    sample_paths: list[str] = [
        str(samples_dir(voice_id) / s.stored_filename) for s in voice.samples
    ]
    for f in files:
        raw = await _read_upload(f, max_bytes)
        try:
            ingested = save_and_validate_sample(voice_id, raw, f.filename)
        except InvalidAudioError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        session.add(
            VoiceSample(
                voice_id=voice_id,
                stored_filename=ingested.stored_filename,
                original_filename=f.filename,
                duration_seconds=ingested.duration_seconds,
                sample_rate=ingested.sample_rate,
            )
        )
        sample_paths.append(str(ingested.path))

    voice.status = VoiceStatus.processing
    session.add(voice)
    session.commit()
    session.refresh(voice)

    _spawn(run_create_voice(voice.id, sample_paths, voice.language))

    return VoiceDetail(
        **_to_summary(voice).model_dump(),
        error_message=None,
        ready_at=None,
        sample_count=len(sample_paths),
    )


@router.get("/{voice_id}/preview")
async def get_preview(voice_id: str, session: Session = Depends(get_session)):
    from fastapi.responses import FileResponse

    voice = session.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice not found")
    p = preview_path(voice_id)
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No preview available yet")
    return FileResponse(p, media_type="audio/wav")


@router.post("/{voice_id}/upgrade", response_model=VoiceDetail)
async def upgrade_voice(
    voice_id: str,
    session: Session = Depends(get_session),
) -> VoiceDetail:
    """Re-process a voice at ``high_fidelity`` tier (e.g. upgrade to RVC)."""
    voice = session.get(Voice, voice_id)
    if voice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice not found")
    if voice.status == VoiceStatus.processing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Voice is already processing — wait for completion or add samples",
        )

    try:
        clone_engine = get_engine(voice.engine_id)
    except UnknownEngineError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Unknown engine '{voice.engine_id}'",
        ) from None

    if not clone_engine.capabilities.fine_tunable:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Engine '{voice.engine_id}' does not support high-fidelity upgrade",
        )
    if not clone_engine.is_ready():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Engine '{voice.engine_id}' is not ready yet",
        )

    if not voice.samples:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Voice has no samples — upload reference audio before upgrading",
        )

    voice.tier = VoiceTier.high_fidelity
    voice.status = VoiceStatus.processing
    voice.error_message = None
    voice.ready_at = None
    session.add(voice)
    session.commit()
    session.refresh(voice)

    sample_paths = [str(samples_dir(voice_id) / s.stored_filename) for s in voice.samples]
    _spawn(run_create_voice(voice.id, sample_paths, voice.language))

    return VoiceDetail(
        **_to_summary(voice).model_dump(),
        error_message=None,
        ready_at=None,
        sample_count=len(voice.samples),
    )
