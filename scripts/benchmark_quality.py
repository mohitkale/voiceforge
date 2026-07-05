#!/usr/bin/env python3
"""Measure clone quality: speaker embedding similarity + optional WER.

Requires the `benchmark` optional extra (and torch, e.g. via the `xtts` extra
or the Docker image):

    pip install -e ".[xtts,benchmark]"
    python scripts/benchmark_quality.py \\
        --reference ref.wav --generated synth.wav \\
        --text "The sentence that was synthesized."

Similarity uses Resemblyzer (speaker-verification embeddings). WER uses
OpenAI Whisper when --text is provided. Output is JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _normalize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _wer(reference: str, hypothesis: str) -> float:
    ref = _normalize_words(reference)
    hyp = _normalize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0

    # Levenshtein on word tokens.
    rows = len(ref) + 1
    cols = len(hyp) + 1
    dist = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        dist[i][0] = i
    for j in range(cols):
        dist[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            dist[i][j] = min(
                dist[i - 1][j] + 1,
                dist[i][j - 1] + 1,
                dist[i - 1][j - 1] + cost,
            )
    return dist[rows - 1][cols - 1] / len(ref)


def speaker_similarity(reference: Path, generated: Path) -> float:
    import numpy as np
    from resemblyzer import VoiceEncoder, preprocess_wav

    encoder = VoiceEncoder()
    ref_emb = encoder.embed_utterance(preprocess_wav(reference))
    gen_emb = encoder.embed_utterance(preprocess_wav(generated))
    return float((ref_emb @ gen_emb) / (np.linalg.norm(ref_emb) * np.linalg.norm(gen_emb)))


def transcribe(path: Path, *, model: str, device: str) -> str:
    import whisper

    result = whisper.load_model(model, device=device).transcribe(str(path))
    return (result.get("text") or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference", type=Path, required=True, help="Reference / source voice WAV"
    )
    parser.add_argument(
        "--generated", type=Path, required=True, help="Synthesized WAV to score"
    )
    parser.add_argument(
        "--text",
        help="Ground-truth transcript of --generated (enables WER via Whisper)",
    )
    parser.add_argument(
        "--whisper-model", default="base", help="Whisper model size (default: base)"
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Torch device for Resemblyzer/Whisper (cpu or cuda)",
    )
    args = parser.parse_args()

    for label, p in ("reference", args.reference), ("generated", args.generated):
        if not p.is_file():
            print(json.dumps({"error": f"{label} file not found: {p}"}), file=sys.stderr)
            sys.exit(1)

    report: dict = {
        "reference": str(args.reference.resolve()),
        "generated": str(args.generated.resolve()),
    }

    try:
        sim = speaker_similarity(args.reference, args.generated)
        report["speaker_similarity"] = round(sim, 4)
        report["speaker_similarity_pct"] = round(sim * 100, 1)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": f"speaker similarity failed: {exc}"}), file=sys.stderr)
        sys.exit(1)

    if args.text:
        try:
            hypothesis = transcribe(args.generated, model=args.whisper_model, device=args.device)
            wer = _wer(args.text, hypothesis)
            report["whisper_transcript"] = hypothesis
            report["reference_text"] = args.text
            report["wer"] = round(wer, 4)
            report["wer_pct"] = round(wer * 100, 1)
        except Exception as exc:  # noqa: BLE001
            report["wer_error"] = str(exc)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
