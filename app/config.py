"""Application settings, loaded from environment variables / `.env`.

Mirrors Reel Studio's convention of one bearer token gating everything
beyond localhost (`MCP_API_TOKEN` there, `VOICEFORGE_API_TOKEN` here).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VOICEFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8089

    # Bearer token required on every /v1/* request when set. Leave unset only
    # for pure localhost/dev use — the app logs a loud warning if it is.
    api_token: str | None = None

    # Comma-separated list of allowed CORS origins, e.g.
    # "http://localhost:3000,https://reel.example.com". Empty = no cross-origin
    # requests are allowed (same-origin / server-to-server / curl still work).
    cors_origins: str = ""

    data_dir: Path = Path("data")
    models_dir: Path = Path("models")

    # "cpu", "cuda", or "auto" (use CUDA if torch reports it's available).
    device: str = "auto"

    # Upload / request limits — deliberately conservative for a local-first,
    # single-user service so one bad request can't exhaust disk or CPU/GPU.
    max_upload_mb: int = 50
    max_samples_per_voice: int = 10
    max_synth_chars: int = 5000
    min_sample_seconds: float = 3.0
    max_sample_seconds: float = 600.0

    # Only one heavy ML job (training/synthesis) runs at a time by default —
    # protects CPU-only / small-GPU hosts from being overwhelmed.
    max_concurrent_jobs: int = 1

    # Trim silence / normalize reference uploads before cloning (M2).
    preprocess_samples: bool = True

    log_level: str = "info"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_path(self) -> Path:
        return self.data_dir / "voiceforge.sqlite3"

    @property
    def voices_dir(self) -> Path:
        return self.data_dir / "voices"


@lru_cache
def get_settings() -> Settings:
    return Settings()
