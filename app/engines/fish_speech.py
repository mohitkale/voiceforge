"""Fish Speech — self-hosted open-weights voice cloning (no Fish Audio cloud).

Talks to a local Fish Speech / fish-speech HTTP API (default
``VOICEFORGE_FISH_SPEECH_URL``, e.g. http://127.0.0.1:8080). This keeps the
main VoiceForge venv free of Fish Speech's heavy pins while staying
local-first (no API keys).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import shutil
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.config import get_settings
from app.engines.asr import map_asr_language, pick_longest_sample, transcribe_reference_audio
from app.engines.base import (
    CloneCapabilities,
    EngineError,
    ProgressFn,
    SynthesizeOptions,
    Tier,
    VoiceArtifact,
)
from app.storage import artifacts_dir

logger = logging.getLogger("voiceforge.engines.fish_speech")

SUPPORTED_LANGUAGES = [
    "en", "zh", "ja", "ko", "de", "fr", "es", "it", "pt", "ru",
    "ar", "hi", "th", "vi", "id", "nl", "pl", "tr",
]


def _validate_sidecar_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise EngineError(
            "VOICEFORGE_FISH_SPEECH_URL must be an http(s) URL "
            "(e.g. http://127.0.0.1:8080)"
        )
    return url.rstrip("/")


class FishSpeechEngine:
    id = "fish-speech"
    label = "Fish Speech (self-hosted open weights)"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=5.0,
        recommended_sample_seconds=15.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=False,
        license="Check Fish Audio / fish-speech upstream (open weights; not cloud API)",
        approx_vram_gb=8.0,
    )

    def is_ready(self) -> bool:
        raw = (get_settings().fish_speech_url or "").strip()
        if not raw:
            return False
        try:
            url = _validate_sidecar_url(raw)
        except EngineError:
            return False
        try:
            req = Request(f"{url}/v1/health", method="GET")  # noqa: S310
            with urlopen(req, timeout=2) as resp:  # noqa: S310
                return 200 <= resp.status < 300
        except Exception:
            try:
                req = Request(url, method="GET")  # noqa: S310
                with urlopen(req, timeout=2) as resp:  # noqa: S310
                    return resp.status < 500
            except Exception:
                return False

    def _resolve_device(self) -> str:
        settings = get_settings()
        if settings.device != "auto":
            return settings.device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    async def create_voice(
        self,
        voice_id: str,
        sample_paths: list[Path],
        tier: Tier,
        language: str,
        on_progress: ProgressFn | None = None,
    ) -> VoiceArtifact:
        if not sample_paths:
            raise EngineError("At least one reference sample is required")
        raw = (get_settings().fish_speech_url or "").strip()
        if not raw:
            raise EngineError(
                "Fish Speech sidecar URL is not configured — set "
                "VOICEFORGE_FISH_SPEECH_URL to your local fish-speech API "
                "(e.g. http://127.0.0.1:8080)"
            )
        _validate_sidecar_url(raw)

        async def report(msg: str, extra: dict | None = None) -> None:
            if on_progress:
                await on_progress(msg, extra)

        await report("caching_reference")
        ref_source = pick_longest_sample(sample_paths)
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_audio = out_dir / "fish_ref.wav"
        shutil.copy2(ref_source, ref_audio)

        await report("transcribing_reference")
        asr_language = map_asr_language(language)
        device = self._resolve_device()

        def _transcribe() -> str:
            text = transcribe_reference_audio(
                str(ref_audio),
                language=asr_language,
                device=device,
            )
            if not (text or "").strip():
                raise EngineError(
                    "Could not transcribe the reference audio — Fish Speech "
                    "needs ref_text; try a clearer clip with intelligible speech"
                )
            return text.strip()

        loop = asyncio.get_running_loop()
        try:
            ref_text = await loop.run_in_executor(None, _transcribe)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Reference transcription failed: {exc}") from exc

        await report("done")
        settings = get_settings()
        return VoiceArtifact(
            engine_id=self.id,
            tier=tier,
            data={
                "ref_audio_path": str(ref_audio.relative_to(settings.data_dir)),
                "ref_text": ref_text,
                "language": language,
            },
        )

    async def synthesize(
        self,
        voice_id: str,
        artifact: VoiceArtifact,
        text: str,
        opts: SynthesizeOptions,
    ) -> bytes:
        raw = (get_settings().fish_speech_url or "").strip()
        if not raw:
            raise EngineError("VOICEFORGE_FISH_SPEECH_URL is not set")
        base = _validate_sidecar_url(raw)

        ref_rel = artifact.data.get("ref_audio_path")
        ref_text = artifact.data.get("ref_text")
        if not ref_rel or not ref_text:
            raise EngineError("Voice is missing Fish Speech reference audio or transcript")

        ref_path = get_settings().data_dir / ref_rel
        if not ref_path.exists():
            raise EngineError("Cached reference audio is missing on disk")

        ref_b64 = base64.b64encode(ref_path.read_bytes()).decode("ascii")
        payload = {
            "text": text,
            "reference_audio": ref_b64,
            "reference_text": ref_text,
            "format": "wav",
        }

        def _post() -> bytes:
            body = json.dumps(payload).encode("utf-8")
            req = Request(  # noqa: S310
                f"{base}/v1/tts",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(req, timeout=600) as resp:  # noqa: S310
                    return resp.read()
            except HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:500]
                raise EngineError(f"Fish Speech API error {exc.code}: {detail}") from exc
            except URLError as exc:
                raise EngineError(
                    f"Fish Speech sidecar unreachable at {base}: {exc.reason}"
                ) from exc

        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, _post)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Synthesis failed: {exc}") from exc

        if len(data) < 44 or data[:4] != b"RIFF":
            raise EngineError(
                "Fish Speech sidecar did not return WAV bytes — configure the "
                "server to emit format=wav"
            )
        return data
