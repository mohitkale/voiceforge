from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import engines, events, metrics, providers, synth, voices
from app.config import get_settings
from app.db import init_db
from app.engine_readiness import get_health_counts, refresh_readiness, start_warmup
from app.logging_setup import configure_logging
from app.middleware import RequestLoggingMiddleware
from app.schemas import HealthResponse
from app.security import SecurityHeadersMiddleware

logger = logging.getLogger("voiceforge")

_STATIC_DIR = Path(__file__).resolve().parent / "static"

OPENAPI_TAGS = [
    {
        "name": "engines",
        "description": "List registered cloning engines and their capabilities.",
    },
    {
        "name": "providers",
        "description": "List side-effect-free provider manifests and runtime support.",
    },
    {
        "name": "voices",
        "description": "Create, list, upgrade, and manage cloned voices.",
    },
    {
        "name": "events",
        "description": "Server-Sent Events stream for voice-processing progress.",
    },
    {
        "name": "synthesize",
        "description": "Generate speech WAV audio from a ready voice.",
    },
    {
        "name": "metrics",
        "description": "Lightweight in-process counters since service startup.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    init_db()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)

    if not settings.api_token:
        logger.warning(
            "VOICEFORGE_API_TOKEN is not set — the API is UNAUTHENTICATED. "
            "This is fine for pure localhost/dev use only. Set "
            "VOICEFORGE_API_TOKEN before exposing this service beyond localhost."
        )
    if settings.watermark_enabled:
        logger.info(
            "Synth watermarking enabled (strength=%.4f)",
            settings.watermark_strength,
        )
    refresh_readiness()
    await start_warmup(settings.warmup_engine_ids)
    yield


app = FastAPI(
    title="VoiceForge",
    description=(
        "Local-first, open-source, multi-engine voice cloning service.\n\n"
        "**Web UI:** open `/` for the Docker-hosted studio.\n\n"
        "**Auth:** Bearer token on `/v1/*` when `VOICEFORGE_API_TOKEN` is set.\n\n"
        "**Engines:** OpenVoice V2, F5-TTS, XTTS-v2, Chatterbox, Qwen3-TTS, "
        "VoxCPM2 (opt-in), Fish Speech, CosyVoice 3, IndexTTS2, RVC.\n\n"
        "See the project README for licensing, consent, and deployment notes."
    ),
    version="0.3.1",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

_settings = get_settings()
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
if _settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

app.include_router(engines.router)
app.include_router(providers.router)
app.include_router(voices.router)
app.include_router(events.router)
app.include_router(synth.router)
app.include_router(metrics.router)

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )
    schema.setdefault("info", {})["license"] = {
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    }
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/", include_in_schema=False)
async def studio_ui() -> FileResponse:
    """Browser studio for cloning and synthesis (served from the same container)."""
    index = _STATIC_DIR / "index.html"
    return FileResponse(index)


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz() -> HealthResponse:
    """Liveness probe — no auth required."""
    ready, total = get_health_counts()
    return HealthResponse(
        status="ok",
        service="voiceforge",
        version=app.version,
        engines_ready=ready,
        engines_total=total,
    )
