"""Bearer-token auth for every `/v1/*` route, plus a couple of hardening
helpers (security headers, a job-concurrency guard for heavy ML work).

Pattern mirrors Reel Studio's single shared-secret bearer token
(`MCP_API_TOKEN`): one token, compared in constant time, required whenever the
service isn't purely localhost-only.
"""

from __future__ import annotations

import asyncio
import logging
import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

logger = logging.getLogger("voiceforge.security")

_bearer = HTTPBearer(auto_error=False)


async def auth_dependency(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """FastAPI dependency: enforces the bearer token when one is configured.

    When no token is configured, the service is assumed to be reachable only
    from localhost/dev — this is logged loudly at startup, not silently.
    """
    settings = get_settings()
    if not settings.api_token:
        return

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(credentials.credentials, settings.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defense-in-depth headers; this API returns JSON/audio, never HTML, but
    these cost nothing and block a few classes of browser-based mischief if
    the API is ever proxied alongside a UI."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


class JobLimiter:
    """Caps concurrent heavy ML jobs (voice creation, synthesis) so a
    CPU-only or small-GPU host can't be driven into the ground by concurrent
    requests. A local-first, single-user tool has no need for a real queue."""

    def __init__(self, max_concurrent: int) -> None:
        self._sem = asyncio.Semaphore(max(1, max_concurrent))

    async def __aenter__(self) -> None:
        await self._sem.acquire()

    async def __aexit__(self, *exc_info: object) -> None:
        self._sem.release()


_job_limiter: JobLimiter | None = None


def get_job_limiter() -> JobLimiter:
    global _job_limiter
    if _job_limiter is None:
        _job_limiter = JobLimiter(get_settings().max_concurrent_jobs)
    return _job_limiter
