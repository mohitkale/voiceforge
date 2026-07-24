#!/usr/bin/env python3
"""Isolated local-only Qwen3-ASR transcription and alignment worker."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

_LANGUAGE_NAMES = {
    "ar": "Arabic",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "fa": "Persian",
    "fi": "Finnish",
    "fil": "Filipino",
    "fr": "French",
    "hi": "Hindi",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "mk": "Macedonian",
    "ms": "Malay",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sv": "Swedish",
    "th": "Thai",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "yue": "Cantonese",
    "zh": "Chinese",
}


def emit_error(message: str) -> None:
    print(json.dumps({"type": "error", "message": message}), flush=True)


def _torch_options(device: str):
    import torch

    resolved = device
    if device == "auto":
        if torch.cuda.is_available():
            resolved = "cuda"
        elif torch.backends.mps.is_available():
            resolved = "mps"
        else:
            resolved = "cpu"
    device_map = "cuda:0" if resolved == "cuda" else resolved
    dtype = torch.bfloat16 if resolved == "cuda" else torch.float32
    return device_map, dtype


def _language(value: str | None) -> str | None:
    if not value:
        return None
    code = value.split("-")[0].lower()
    return _LANGUAGE_NAMES.get(code, value)


def _timestamp_payload(items) -> list[dict]:
    payload: list[dict] = []
    for item in items or []:
        payload.append(
            {
                "text": str(getattr(item, "text", "")),
                "start_seconds": float(
                    getattr(item, "start_time", getattr(item, "start_seconds", 0.0))
                ),
                "end_seconds": float(
                    getattr(item, "end_time", getattr(item, "end_seconds", 0.0))
                ),
            }
        )
    return payload


def cmd_ping(_args: argparse.Namespace) -> int:
    print("ok", flush=True)
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    model_dir = Path(args.model_dir)
    audio = Path(args.audio)
    output = Path(args.output_json)
    if not model_dir.is_dir() or not audio.is_file():
        emit_error("transcribe requires existing local model-dir and audio paths")
        return 1
    try:
        from qwen_asr import Qwen3ASRModel

        device_map, dtype = _torch_options(args.device)
        kwargs: dict = {
            "dtype": dtype,
            "device_map": device_map,
            "local_files_only": True,
            "max_inference_batch_size": 1,
            "max_new_tokens": 512,
        }
        if args.timestamps:
            aligner_dir = Path(args.aligner_dir)
            if not aligner_dir.is_dir():
                raise ValueError("--aligner-dir must be an existing local directory")
            kwargs["forced_aligner"] = str(aligner_dir)
            kwargs["forced_aligner_kwargs"] = {
                "dtype": dtype,
                "device_map": device_map,
            }
        model = Qwen3ASRModel.from_pretrained(str(model_dir), **kwargs)
        results = model.transcribe(
            audio=str(audio),
            language=_language(args.language),
            return_time_stamps=args.timestamps,
        )
        result = results[0]
        output.write_text(
            json.dumps(
                {
                    "text": str(getattr(result, "text", "")).strip(),
                    "language": getattr(result, "language", None),
                    "timestamps": _timestamp_payload(getattr(result, "time_stamps", [])),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        emit_error(f"Qwen3-ASR transcription failed: {exc}")
        traceback.print_exc()
        return 1


def cmd_align(args: argparse.Namespace) -> int:
    aligner_dir = Path(args.aligner_dir)
    audio = Path(args.audio)
    output = Path(args.output_json)
    if not aligner_dir.is_dir() or not audio.is_file():
        emit_error("align requires existing local aligner-dir and audio paths")
        return 1
    try:
        from qwen_asr import Qwen3ForcedAligner

        device_map, dtype = _torch_options(args.device)
        model = Qwen3ForcedAligner.from_pretrained(
            str(aligner_dir),
            dtype=dtype,
            device_map=device_map,
            local_files_only=True,
        )
        results = model.align(
            audio=str(audio),
            text=args.text,
            language=_language(args.language),
        )
        output.write_text(
            json.dumps({"timestamps": _timestamp_payload(results[0])}, ensure_ascii=False),
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        emit_error(f"Qwen3 forced alignment failed: {exc}")
        traceback.print_exc()
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ping")

    transcribe = sub.add_parser("transcribe")
    transcribe.add_argument("--audio", required=True)
    transcribe.add_argument("--model-dir", required=True)
    transcribe.add_argument("--language")
    transcribe.add_argument("--timestamps", action="store_true")
    transcribe.add_argument("--aligner-dir")
    transcribe.add_argument("--device", default="auto")
    transcribe.add_argument("--output-json", required=True)

    align = sub.add_parser("align")
    align.add_argument("--audio", required=True)
    align.add_argument("--text", required=True)
    align.add_argument("--language", required=True)
    align.add_argument("--aligner-dir", required=True)
    align.add_argument("--device", default="auto")
    align.add_argument("--output-json", required=True)

    args = parser.parse_args()
    if args.command == "ping":
        return cmd_ping(args)
    if args.command == "transcribe":
        return cmd_transcribe(args)
    if args.command == "align":
        return cmd_align(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
