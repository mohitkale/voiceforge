from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.db_models import Voice, VoiceStatus
from app.engines.base import EngineError, SynthesizeOptions, VoiceArtifact
from app.engines.registry import UnknownEngineError, get_engine
from app.metrics import get_metrics
from app.schemas import SynthesizeRequest
from app.security import auth_dependency, get_job_limiter
from app.watermark import apply_watermark_to_wav

router = APIRouter(prefix="/v1", tags=["synthesize"], dependencies=[Depends(auth_dependency)])


@router.post(
    "/synthesize",
    summary="Synthesize speech",
    response_description="16-bit PCM WAV audio",
)
async def synthesize(
    body: SynthesizeRequest,
    session: Session = Depends(get_session),
) -> Response:
    settings = get_settings()
    if len(body.text) > settings.max_synth_chars:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Text too long (max {settings.max_synth_chars} characters)",
        )

    voice = session.get(Voice, body.voice_id)
    if voice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice not found")
    if voice.status != VoiceStatus.ready:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Voice is not ready yet (status: {voice.status.value})"
        )

    try:
        clone_engine = get_engine(voice.engine_id)
    except UnknownEngineError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Voice engine no longer registered"
        ) from None

    artifact = VoiceArtifact.model_validate(voice.artifact)
    opts = SynthesizeOptions(
        sample_rate=body.sample_rate,
        speed=body.speed,
        language=body.language or voice.language,
    )

    async with get_job_limiter():
        get_metrics().inc("synth_requests")
        try:
            wav_bytes = await clone_engine.synthesize(voice.id, artifact, body.text, opts)
        except EngineError as exc:
            get_metrics().inc("synth_errors")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    if settings.watermark_enabled:
        wav_bytes = apply_watermark_to_wav(
            wav_bytes,
            voice_id=voice.id,
            strength=settings.watermark_strength,
        )

    return Response(content=wav_bytes, media_type="audio/wav")
