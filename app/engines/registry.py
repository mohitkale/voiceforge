"""Engine registry — maps engine id -> lazily-constructed singleton instance.

Adding a new engine later is one new file (implementing `CloneEngine`) plus
one entry in `_FACTORIES` here; nothing else in the app references a specific
engine's SDK directly.
"""

from __future__ import annotations

from collections.abc import Callable

from app.engines.base import CloneEngine
from app.engines.chatterbox import ChatterboxEngine
from app.engines.cosyvoice_3 import CosyVoice3Engine
from app.engines.f5_tts import F5TtsEngine
from app.engines.fish_speech import FishSpeechEngine
from app.engines.indextts_2 import IndexTts2Engine
from app.engines.openvoice_v2 import OpenVoiceV2Engine
from app.engines.qwen3_tts import Qwen3TtsEngine
from app.engines.rvc import RvcEngine
from app.engines.xtts_v2 import XttsV2Engine

_FACTORIES: dict[str, Callable[[], CloneEngine]] = {
    "xtts-v2": XttsV2Engine,
    "f5-tts": F5TtsEngine,
    "openvoice-v2": OpenVoiceV2Engine,
    "rvc": RvcEngine,
    "chatterbox": ChatterboxEngine,
    "qwen3-tts": Qwen3TtsEngine,
    "fish-speech": FishSpeechEngine,
    "cosyvoice-3": CosyVoice3Engine,
    "indextts-2": IndexTts2Engine,
}

_instances: dict[str, CloneEngine] = {}


class UnknownEngineError(KeyError):
    pass


def get_engine(engine_id: str) -> CloneEngine:
    if engine_id not in _FACTORIES:
        raise UnknownEngineError(engine_id)
    instance = _instances.get(engine_id)
    if instance is None:
        instance = _FACTORIES[engine_id]()
        _instances[engine_id] = instance
    return instance


def list_engines() -> list[CloneEngine]:
    return [get_engine(engine_id) for engine_id in _FACTORIES]


def engine_ids() -> list[str]:
    return list(_FACTORIES.keys())
