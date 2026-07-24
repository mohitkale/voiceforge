"""Model-independent contracts for repeatable VoiceForge benchmarks."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from pydantic import BaseModel, Field

LanguageGroup = Literal["english", "hindi-devanagari", "hindi-romanized", "hinglish"]


class BenchmarkCase(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    language_group: LanguageGroup
    language: str
    text: str = Field(min_length=1)
    emotion: str = "neutral"
    tags: list[str] = Field(default_factory=list)


class BenchmarkPlan(BaseModel):
    schema_version: str = "voiceforge-benchmark/v1"
    provider_id: str
    model_revision: str
    seed: int
    hardware: str
    suite_sha256: str
    cases: list[BenchmarkCase]


class BenchmarkObservation(BaseModel):
    case_id: str
    generated_audio: Path
    hypothesis: str | None = None
    latency_seconds: float | None = Field(default=None, ge=0)
    peak_memory_mb: float | None = Field(default=None, ge=0)
    speaker_similarity: float | None = Field(default=None, ge=-1, le=1)
    emotion_score: float | None = Field(default=None, ge=1, le=5)
    notes: str | None = None


class CaseScore(BaseModel):
    case_id: str
    language_group: LanguageGroup
    duration_seconds: float
    peak_dbfs: float | None
    clipped_fraction: float
    wer: float | None = None
    cer: float | None = None
    latency_seconds: float | None = None
    real_time_factor: float | None = None
    peak_memory_mb: float | None = None
    speaker_similarity: float | None = None
    emotion_score: float | None = None


def load_cases(path: Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    ids: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        case = BenchmarkCase.model_validate_json(raw)
        if case.id in ids:
            raise ValueError(f"Duplicate benchmark id '{case.id}' on line {line_number}")
        ids.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError("Benchmark suite contains no cases")
    return cases


def suite_sha256(cases: list[BenchmarkCase]) -> str:
    canonical = "\n".join(
        case.model_dump_json(exclude_none=True) for case in sorted(cases, key=lambda item: item.id)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_plan(
    *,
    provider_id: str,
    model_revision: str,
    seed: int,
    hardware: str,
    cases: list[BenchmarkCase],
) -> BenchmarkPlan:
    return BenchmarkPlan(
        provider_id=provider_id,
        model_revision=model_revision,
        seed=seed,
        hardware=hardware,
        suite_sha256=suite_sha256(cases),
        cases=cases,
    )


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower().strip()


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[\w']+", _normalize(text), flags=re.UNICODE)


def _characters(text: str) -> list[str]:
    return [
        char
        for char in _normalize(text)
        if unicodedata.category(char)[0] in {"L", "M", "N"}
    ]


def _error_rate(reference: list[str], hypothesis: list[str]) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    previous = list(range(len(hypothesis) + 1))
    for row, ref_item in enumerate(reference, start=1):
        current = [row]
        for col, hyp_item in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[col] + 1,
                    previous[col - 1] + (ref_item != hyp_item),
                )
            )
        previous = current
    return previous[-1] / len(reference)


def word_error_rate(reference: str, hypothesis: str) -> float:
    return _error_rate(_word_tokens(reference), _word_tokens(hypothesis))


def character_error_rate(reference: str, hypothesis: str) -> float:
    return _error_rate(_characters(reference), _characters(hypothesis))


def score_observation(case: BenchmarkCase, observation: BenchmarkObservation) -> CaseScore:
    if not observation.generated_audio.is_file():
        raise ValueError(f"Generated audio not found: {observation.generated_audio}")
    wav, sample_rate = sf.read(
        str(observation.generated_audio),
        dtype="float32",
        always_2d=True,
    )
    mono = np.asarray(wav, dtype=np.float32).mean(axis=1)
    duration = len(mono) / sample_rate if sample_rate else 0.0
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    peak_dbfs = float(20 * np.log10(peak)) if peak > 0 else None
    clipped = float(np.mean(np.abs(mono) >= 0.999)) if len(mono) else 0.0
    wer = cer = None
    if observation.hypothesis is not None:
        wer = word_error_rate(case.text, observation.hypothesis)
        cer = character_error_rate(case.text, observation.hypothesis)
    rtf = None
    if observation.latency_seconds is not None and duration > 0:
        rtf = observation.latency_seconds / duration
    return CaseScore(
        case_id=case.id,
        language_group=case.language_group,
        duration_seconds=round(duration, 4),
        peak_dbfs=round(peak_dbfs, 4) if peak_dbfs is not None else None,
        clipped_fraction=round(clipped, 6),
        wer=round(wer, 6) if wer is not None else None,
        cer=round(cer, 6) if cer is not None else None,
        latency_seconds=observation.latency_seconds,
        real_time_factor=round(rtf, 6) if rtf is not None else None,
        peak_memory_mb=observation.peak_memory_mb,
        speaker_similarity=observation.speaker_similarity,
        emotion_score=observation.emotion_score,
    )


def summarize(scores: list[CaseScore]) -> dict:
    groups: dict[str, list[CaseScore]] = defaultdict(list)
    for score in scores:
        groups[score.language_group].append(score)

    def mean(items: list[float | None]) -> float | None:
        values = [item for item in items if item is not None]
        return round(sum(values) / len(values), 6) if values else None

    return {
        "cases_scored": len(scores),
        "groups": {
            name: {
                "count": len(items),
                "mean_wer": mean([item.wer for item in items]),
                "mean_cer": mean([item.cer for item in items]),
                "mean_rtf": mean([item.real_time_factor for item in items]),
                "mean_speaker_similarity": mean(
                    [item.speaker_similarity for item in items]
                ),
                "mean_emotion_score": mean([item.emotion_score for item in items]),
            }
            for name, items in sorted(groups.items())
        },
    }


def load_observations(path: Path) -> list[BenchmarkObservation]:
    return [
        BenchmarkObservation.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def write_json(path: Path, payload: BaseModel | dict | list) -> None:
    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    elif isinstance(payload, list):
        data = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in payload
        ]
    else:
        data = payload
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
