#!/usr/bin/env python3
"""Isolated IndexTTS2 worker — runs in a separate venv from the main app.

Commands:
    ping
    setup --models-dir DIR
    synthesize --model-dir DIR --ref-audio PATH --text TEXT --output PATH
"""

from __future__ import annotations

import argparse
import json
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
    emit("downloading_indextts2")
    try:
        from huggingface_hub import snapshot_download

        target = models_dir / "IndexTTS-2"
        snapshot_download("IndexTeam/IndexTTS-2", local_dir=str(target))
        emit("setup_complete", {"model_dir": str(target)})
    except Exception as exc:
        emit_error(f"IndexTTS2 setup failed: {exc}")
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

    cfg_path = model_dir / "config.yaml"
    if not cfg_path.is_file():
        # Some HF layouts nest config one level deeper.
        candidates = list(model_dir.rglob("config.yaml"))
        if not candidates:
            emit_error(f"config.yaml not found under {model_dir}")
            return 1
        cfg_path = candidates[0]
        model_dir = cfg_path.parent

    emit("loading_model")
    try:
        from indextts.infer_v2 import IndexTTS2
    except Exception as exc:
        emit_error(
            "IndexTTS2 is not installed in this worker venv — install index-tts "
            f"(uv/pip) per upstream docs. Import error: {exc}"
        )
        traceback.print_exc()
        return 1

    try:
        tts = IndexTTS2(
            cfg_path=str(cfg_path),
            model_dir=str(model_dir),
            use_fp16=False,
            use_cuda_kernel=False,
            use_deepspeed=False,
        )
        emit("synthesizing")
        output.parent.mkdir(parents=True, exist_ok=True)
        tts.infer(
            spk_audio_prompt=str(ref_audio),
            text=args.text,
            output_path=str(output),
            verbose=False,
        )
        if not output.is_file():
            emit_error("IndexTTS2 did not write output audio")
            return 1
        emit("done", {"output": str(output)})
    except Exception as exc:
        emit_error(f"IndexTTS2 synthesize failed: {exc}")
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
