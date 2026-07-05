"""XTTS-v2 (Coqui) engine — the MVP zero-shot cloning engine.

Uses the actively maintained community fork published as `coqui-tts` on PyPI
(the original `coqui-ai/TTS` repo is defunct; see README). Heavy imports
(torch, TTS) are deferred to first use so the rest of the service can start
and report accurate `is_ready()`/capabilities even before the ~2GB checkpoint
is downloaded, and so unit tests don't need the ML stack installed at all.

License note: the XTTS-v2 *model weights* are CPML (Coqui Public Model
License) — non-commercial/research use only. The `coqui-tts` *library code*
itself is MPL-2.0. See README's "Licensing & responsible use" section.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.engines.base import (
    CloneCapabilities,
    EngineError,
    ProgressFn,
    SynthesizeOptions,
    Tier,
    VoiceArtifact,
)
from app.engines.wav_output import to_wav_bytes as _to_wav_bytes
from app.storage import artifacts_dir

logger = logging.getLogger("voiceforge.engines.xtts_v2")

XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
XTTS_NATIVE_SAMPLE_RATE = 24000

SUPPORTED_LANGUAGES = [
    "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl",
    "cs", "ar", "zh-cn", "ja", "hu", "ko", "hi",
]


class XttsV2Engine:
    id = "xtts-v2"
    label = "XTTS-v2 (Coqui, community fork)"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=6.0,
        recommended_sample_seconds=20.0,
        languages=SUPPORTED_LANGUAGES,
        requires_gpu=False,
        license="CPML (Coqui Public Model License) — non-commercial/research only",
        approx_vram_gb=4.0,
    )

    def __init__(self) -> None:
        self._tts = None
        self._load_lock: asyncio.Lock | None = None
        self._unavailable_reason: str | None = None

    def _lock(self) -> asyncio.Lock:
        # Created lazily so constructing the engine never requires a running
        # event loop (needed for import-time registry construction / tests).
        if self._load_lock is None:
            self._load_lock = asyncio.Lock()
        return self._load_lock

    def _resolve_device(self) -> str:
        settings = get_settings()
        if settings.device != "auto":
            return settings.device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def is_ready(self) -> bool:
        if self._tts is not None:
            return True
        try:
            import TTS  # noqa: F401
        except Exception as exc:  # pragma: no cover - depends on optional extra
            self._unavailable_reason = (
                "XTTS-v2 dependencies not installed (torch/coqui-tts). "
                f"Import error: {exc}"
            )
            return False
        return True

    async def _ensure_loaded(self):
        if self._tts is not None:
            return self._tts
        async with self._lock():
            if self._tts is not None:
                return self._tts

            settings = get_settings()
            settings.models_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("TTS_HOME", str(settings.models_dir))
            # Non-interactive CPML acceptance — the human-facing consent
            # happens at voice-creation time via the `consent` API field and
            # the README's licensing section, not an interactive TTY prompt
            # that would hang a server process.
            os.environ.setdefault("COQUI_TOS_AGREED", "1")

            def _load():
                try:
                    from TTS.api import TTS
                except Exception as exc:  # pragma: no cover
                    raise EngineError(
                        "XTTS-v2 dependencies are not installed. Install the "
                        "'xtts' extra (torch + coqui-tts) or use the Docker image."
                    ) from exc
                device = self._resolve_device()
                logger.info(
                    "Loading XTTS-v2 onto device=%s (first run may download "
                    "the ~2GB checkpoint)",
                    device,
                )
                return TTS(XTTS_MODEL_NAME).to(device)

            loop = asyncio.get_running_loop()
            self._tts = await loop.run_in_executor(None, _load)
            return self._tts

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

        async def report(msg: str, extra: dict | None = None) -> None:
            if on_progress:
                await on_progress(msg, extra)

        await report("loading_model")
        tts = await self._ensure_loaded()

        await report("extracting_conditioning_latents")
        out_dir = artifacts_dir(voice_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        latents_path = out_dir / "xtts_latents.pt"

        def _compute() -> None:
            import torch

            model = tts.synthesizer.tts_model
            gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
                audio_path=[str(p) for p in sample_paths],
            )
            torch.save(
                {
                    "gpt_cond_latent": gpt_cond_latent,
                    "speaker_embedding": speaker_embedding,
                },
                latents_path,
            )

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _compute)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Failed to extract voice conditioning: {exc}") from exc

        await report("done")
        return VoiceArtifact(
            engine_id=self.id,
            tier=tier,
            data={
                "latents_path": str(latents_path.relative_to(get_settings().data_dir)),
            },
        )

    async def synthesize(
        self,
        voice_id: str,
        artifact: VoiceArtifact,
        text: str,
        opts: SynthesizeOptions,
    ) -> bytes:
        latents_rel = artifact.data.get("latents_path")
        if not latents_rel:
            raise EngineError("Voice has no cached conditioning latents")
        latents_path = get_settings().data_dir / latents_rel
        if not latents_path.exists():
            raise EngineError("Cached conditioning latents are missing on disk")

        tts = await self._ensure_loaded()
        language = (opts.language or "en").split("-")[0]
        target_rate = opts.sample_rate or 44100
        speed = opts.speed or 1.0

        def _synth() -> np.ndarray:
            import torch

            # weights_only=True: this file only ever contains tensors we
            # wrote ourselves, so there's no reason to allow arbitrary
            # pickled objects/code execution on load.
            cached = torch.load(latents_path, weights_only=True)
            model = tts.synthesizer.tts_model
            with torch.no_grad():
                out = model.inference(
                    text=text,
                    language=language,
                    gpt_cond_latent=cached["gpt_cond_latent"],
                    speaker_embedding=cached["speaker_embedding"],
                    speed=speed,
                    enable_text_splitting=True,
                )
            return np.asarray(out["wav"], dtype=np.float32)

        loop = asyncio.get_running_loop()
        try:
            wav = await loop.run_in_executor(None, _synth)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Synthesis failed: {exc}") from exc

        return _to_wav_bytes(wav, source_rate=XTTS_NATIVE_SAMPLE_RATE, target_rate=target_rate)
