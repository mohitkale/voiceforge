#!/usr/bin/env python3
"""Isolated CosyVoice 3 worker — runs in a separate venv from the main app.

Commands:
    ping
    setup --models-dir DIR
    synthesize --model-dir DIR --ref-audio PATH --ref-text TEXT --text TEXT --output PATH
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


def emit(message: str, extra: dict | None = None) -> None:
    print(
        json.dumps({"type": "progress", "message": message, "extra": extra or {}}),
        flush=True,
    )


def emit_error(message: str) -> None:
    print(json.dumps({"type": "error", "message": message}), flush=True)


def cmd_ping(_args: argparse.Namespace) -> int:
    print("ok", flush=True)
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    models_dir = Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    emit("downloading_cosyvoice3")
    try:
        from huggingface_hub import snapshot_download

        target = models_dir / "Fun-CosyVoice3-0.5B"
        snapshot_download(
            "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
            local_dir=str(target),
        )
        emit("setup_complete", {"model_dir": str(target)})
    except Exception as exc:
        emit_error(f"CosyVoice setup failed: {exc}")
        traceback.print_exc()
        return 1
    return 0


def cmd_synthesize(args: argparse.Namespace) -> int:
    model_dir = Path(args.model_dir)
    ref_audio = Path(args.ref_audio)
    output = Path(args.output)
    if not ref_audio.is_file():
        emit_error(f"Reference audio not found: {ref_audio}")
        return 1
    if not model_dir.exists():
        emit_error(f"Model dir not found: {model_dir}")
        return 1

    emit("loading_model")
    try:
        # CosyVoice repo layout expects Matcha-TTS on sys.path when installed from source.
        matcha = model_dir.parent / "third_party" / "Matcha-TTS"
        if matcha.is_dir():
            sys.path.insert(0, str(matcha))

        import torchaudio
        from cosyvoice.cli.cosyvoice import AutoModel
    except Exception as exc:
        emit_error(
            "CosyVoice is not installed in this worker venv — clone FunAudioLLM/CosyVoice "
            f"and pip install its requirements. Import error: {exc}"
        )
        traceback.print_exc()
        return 1

    try:
        cosyvoice = AutoModel(model_dir=str(model_dir))
        emit("synthesizing")
        chunks = []
        prompt_text = args.ref_text or "You are a helpful assistant.<|endofprompt|>"
        for _i, item in enumerate(
            cosyvoice.inference_zero_shot(
                args.text,
                prompt_text,
                str(ref_audio),
                stream=False,
            )
        ):
            chunks.append(item["tts_speech"])
        if not chunks:
            emit_error("CosyVoice produced no audio")
            return 1
        speech = chunks[0] if len(chunks) == 1 else chunks[0]
        output.parent.mkdir(parents=True, exist_ok=True)
        torchaudio.save(str(output), speech, cosyvoice.sample_rate)
        emit("done", {"output": str(output)})
    except Exception as exc:
        emit_error(f"CosyVoice synthesize failed: {exc}")
        traceback.print_exc()
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping")

    p_setup = sub.add_parser("setup")
    p_setup.add_argument("--models-dir", required=True)

    p_synth = sub.add_parser("synthesize")
    p_synth.add_argument("--model-dir", required=True)
    p_synth.add_argument("--ref-audio", required=True)
    p_synth.add_argument("--ref-text", default="")
    p_synth.add_argument("--text", required=True)
    p_synth.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.command == "ping":
        return cmd_ping(args)
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "synthesize":
        return cmd_synthesize(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
