#!/usr/bin/env python3
"""Create and score reproducible VoiceForge benchmark runs without loading models.

Examples:
  python scripts/benchmark_suite.py plan --provider voxcpm2 \
    --model-revision 9454c2d --hardware "MacBook M-series, 16 GB" --output run.json

  python scripts/benchmark_suite.py score --plan run.json \
    --observations observations.jsonl --output report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.benchmarking import (  # noqa: E402
    BenchmarkPlan,
    build_plan,
    load_cases,
    load_observations,
    score_observation,
    summarize,
    write_json,
)

DEFAULT_SUITE = Path(__file__).resolve().parents[1] / "benchmarks" / "prompts.v1.jsonl"


def plan_command(args: argparse.Namespace) -> int:
    cases = load_cases(args.suite)
    plan = build_plan(
        provider_id=args.provider,
        model_revision=args.model_revision,
        seed=args.seed,
        hardware=args.hardware,
        cases=cases,
    )
    write_json(args.output, plan)
    print(json.dumps({"plan": str(args.output), "cases": len(cases), "sha256": plan.suite_sha256}))
    return 0


def score_command(args: argparse.Namespace) -> int:
    plan = BenchmarkPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    observations = load_observations(args.observations)
    cases = {case.id: case for case in plan.cases}
    seen: set[str] = set()
    scores = []
    for observation in observations:
        if observation.case_id in seen:
            raise ValueError(f"Duplicate observation for case '{observation.case_id}'")
        seen.add(observation.case_id)
        if observation.case_id not in cases:
            raise ValueError(f"Unknown benchmark case '{observation.case_id}'")
        scores.append(score_observation(cases[observation.case_id], observation))
    payload = {
        "schema_version": "voiceforge-benchmark-report/v1",
        "plan": plan.model_dump(mode="json"),
        "scores": [score.model_dump(mode="json") for score in scores],
        "summary": summarize(scores),
        "missing_cases": sorted(set(cases) - seen),
    }
    write_json(args.output, payload)
    print(json.dumps({"report": str(args.output), "cases_scored": len(scores)}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--provider", required=True)
    plan.add_argument("--model-revision", required=True)
    plan.add_argument("--hardware", required=True)
    plan.add_argument("--seed", type=int, default=42)
    plan.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    plan.add_argument("--output", type=Path, required=True)

    score = sub.add_parser("score")
    score.add_argument("--plan", type=Path, required=True)
    score.add_argument("--observations", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        return plan_command(args)
    if args.command == "score":
        return score_command(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
