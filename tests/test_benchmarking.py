from pathlib import Path

import numpy as np
import soundfile as sf

from app.benchmarking import (
    BenchmarkCase,
    BenchmarkObservation,
    build_plan,
    character_error_rate,
    load_cases,
    score_observation,
    suite_sha256,
    word_error_rate,
)

SUITE = Path(__file__).resolve().parents[1] / "benchmarks" / "prompts.v1.jsonl"


def test_benchmark_suite_has_all_required_language_groups():
    cases = load_cases(SUITE)
    groups = {case.language_group for case in cases}
    assert groups == {"english", "hindi-devanagari", "hindi-romanized", "hinglish"}
    assert len(cases) >= 20
    assert len({case.id for case in cases}) == len(cases)


def test_suite_hash_and_plan_are_deterministic():
    cases = load_cases(SUITE)
    first = suite_sha256(cases)
    second = suite_sha256(list(reversed(cases)))
    assert first == second
    plan = build_plan(
        provider_id="voxcpm2",
        model_revision="9454c2d",
        seed=42,
        hardware="test",
        cases=cases,
    )
    assert plan.suite_sha256 == first
    assert plan.schema_version == "voiceforge-benchmark/v1"


def test_unicode_word_and_character_error_rates():
    assert word_error_rate("hello world", "hello world") == 0
    assert word_error_rate("hello world", "hello there") == 0.5
    assert character_error_rate("यह आवाज़", "यह आवाज़") == 0
    assert character_error_rate("आवाज़", "आवाज") > 0


def test_audio_score_uses_existing_output_only(tmp_path):
    audio = tmp_path / "generated.wav"
    sample_rate = 16000
    wav = np.zeros(sample_rate, dtype=np.float32)
    sf.write(audio, wav, sample_rate, subtype="PCM_16")
    case = BenchmarkCase(
        id="test-case",
        language_group="english",
        language="en",
        text="hello world",
    )
    score = score_observation(
        case,
        BenchmarkObservation(
            case_id=case.id,
            generated_audio=audio,
            hypothesis="hello world",
            latency_seconds=0.5,
        ),
    )
    assert score.duration_seconds == 1.0
    assert score.wer == 0
    assert score.real_time_factor == 0.5
