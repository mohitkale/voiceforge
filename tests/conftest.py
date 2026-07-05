"""Test configuration.

Tests never require torch/coqui-tts: a lightweight `FakeEngine` (pure
numpy/soundfile, both core deps) is registered alongside the real `xtts-v2`
entry so the API/DB/validation/auth layers are fully exercised without a
multi-GB model download.
"""

from __future__ import annotations

import io
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="voiceforge-test-")
os.environ.setdefault("VOICEFORGE_DATA_DIR", os.path.join(_TMP, "data"))
os.environ.setdefault("VOICEFORGE_MODELS_DIR", os.path.join(_TMP, "models"))
os.environ.setdefault("VOICEFORGE_API_TOKEN", "")
os.environ.setdefault("VOICEFORGE_MAX_CONCURRENT_JOBS", "4")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
import soundfile as sf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.engines import registry as engine_registry  # noqa: E402
from app.engines.base import CloneCapabilities, VoiceArtifact  # noqa: E402
from app.main import app  # noqa: E402

FAKE_ENGINE_ID = "fake-engine"


class FakeEngine:
    id = FAKE_ENGINE_ID
    label = "Fake Engine (tests only)"
    capabilities = CloneCapabilities(
        zero_shot=True,
        fine_tunable=False,
        min_sample_seconds=1.0,
        recommended_sample_seconds=5.0,
        languages=["en"],
        requires_gpu=False,
        license="MIT",
        approx_vram_gb=None,
    )

    def is_ready(self) -> bool:
        return True

    async def create_voice(self, voice_id, sample_paths, tier, language, on_progress=None):
        if on_progress:
            await on_progress("processing")
        return VoiceArtifact(engine_id=self.id, tier=tier, data={"ok": True})

    async def synthesize(self, voice_id, artifact, text, opts):
        sample_rate = opts.sample_rate or 44100
        wav = np.zeros(sample_rate // 10, dtype=np.float32)
        buf = io.BytesIO()
        sf.write(buf, wav, samplerate=sample_rate, subtype="PCM_16", format="WAV")
        return buf.getvalue()


class FailingEngine(FakeEngine):
    id = "failing-engine"
    label = "Failing Engine (tests only)"

    async def create_voice(self, voice_id, sample_paths, tier, language, on_progress=None):
        from app.engines.base import EngineError

        raise EngineError("synthetic failure for tests")


engine_registry._FACTORIES.setdefault(FAKE_ENGINE_ID, FakeEngine)
engine_registry._FACTORIES.setdefault("failing-engine", FailingEngine)


def make_wav_bytes(duration_seconds: float = 3.0, sample_rate: int = 22050) -> bytes:
    t = np.arange(int(duration_seconds * sample_rate), dtype=np.float32) / sample_rate
    samples = (0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, samples, samplerate=sample_rate, subtype="PCM_16", format="WAV")
    return buf.getvalue()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def settings():
    return get_settings()


@pytest.fixture()
def auth_headers(settings):
    if settings.api_token:
        return {"Authorization": f"Bearer {settings.api_token}"}
    return {}
