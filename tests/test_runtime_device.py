from types import SimpleNamespace

import pytest

from app.engines.qwen3_tts import Qwen3TtsEngine
from app.runtime_device import resolve_torch_device, transformers_device_map


def _fake_torch(*, cuda: bool, mps: bool):
    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)),
    )


def test_auto_device_prefers_cuda_then_mps_then_cpu():
    assert resolve_torch_device("auto", _fake_torch(cuda=True, mps=True)) == "cuda"
    assert resolve_torch_device("auto", _fake_torch(cuda=False, mps=True)) == "mps"
    assert resolve_torch_device("auto", _fake_torch(cuda=False, mps=False)) == "cpu"


def test_explicit_mps_is_not_mapped_to_cuda():
    assert resolve_torch_device("mps") == "mps"
    assert transformers_device_map("mps") == "mps"
    assert transformers_device_map("cuda") == "cuda:0"


def test_unknown_device_rejected():
    with pytest.raises(ValueError, match="Unsupported device"):
        resolve_torch_device("metal")


def test_qwen_tts_is_not_ready_without_local_snapshot(monkeypatch):
    settings = SimpleNamespace(qwen3_tts_model_dir=None)
    monkeypatch.setattr("app.engines.qwen3_tts.get_settings", lambda: settings)

    assert Qwen3TtsEngine().is_ready() is False
