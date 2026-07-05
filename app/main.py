from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import engines, events, synth, voices
from app.config import get_settings
from app.db import init_db
from app.security import SecurityHeadersMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voiceforge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.getLogger().setLevel(settings.log_level.upper())
    init_db()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)

    if not settings.api_token:
        logger.warning(
            "VOICEFORGE_API_TOKEN is not set — the API is UNAUTHENTICATED. "
            "This is fine for pure localhost/dev use only. Set "
            "VOICEFORGE_API_TOKEN before exposing this service beyond localhost."
        )
    yield


app = FastAPI(
    title="VoiceForge",
    description=(
        "Local-first, open-source, multi-engine voice cloning service. "
        "See /docs for the full API, and the README for licensing/consent notes."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(SecurityHeadersMiddleware)
if _settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(engines.router)
app.include_router(voices.router)
app.include_router(events.router)
app.include_router(synth.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "voiceforge"}
