#!/usr/bin/env python3
"""Isolated Chatterbox worker — separate venv (numpy<2 / torch pins).

Commands:
    ping
    setup
    synthesize --ref-audio PATH --text TEXT --output PATH [--device cpu|cuda]
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


def cmd_setup(_args: argparse.Namespace) -> int:
    emit("loading_chatterbox")
    try:
        from chatterbox.tts import ChatterboxTTS

        device = "cpu"
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
        except Exception:
            # Torch may be missing or CUDA unavailable in the worker venv.
            device = "cpu"
        ChatterboxTTS.from_pretrained(device=device)
        emit("setup_complete")
    except Exception as exc:
        emit_error(f"Chatterbox setup failed: {exc}")
        traceback.print_exc()
        return 1
    return 0


def _synthesize_with_model(model, ref_audio: Path, text: str, output: Path) -> None:
    import numpy as np
    import soundfile as sf

    emit("synthesizing")
    wav = model.generate(text, audio_prompt_path=str(ref_audio))
    if hasattr(wav, "cpu"):
        arr = wav.squeeze().detach().cpu().numpy().astype("float32")
    else:
        arr = np.asarray(wav, dtype="float32").squeeze()
    sr = int(getattr(model, "sr", 24000))
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), arr, sr)
    emit("done", {"output": str(output)})


def cmd_synthesize(args: argparse.Namespace) -> int:
    ref_audio = Path(args.ref_audio)
    output = Path(args.output)
    if not ref_audio.is_file():
        emit_error(f"Reference audio not found: {ref_audio}")
        return 1

    emit("loading_model")
    try:
        from chatterbox.tts import ChatterboxTTS
    except Exception as exc:
        emit_error(
            "chatterbox-tts is not installed in this worker venv — "
            f"pip install -r requirements-chatterbox.txt. Import error: {exc}"
        )
        traceback.print_exc()
        return 1

    try:
        device = args.device
        if device == "auto":
            try:
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        model = ChatterboxTTS.from_pretrained(device=device)
        _synthesize_with_model(model, ref_audio, args.text, output)
    except Exception as exc:
        emit_error(f"Chatterbox synthesize failed: {exc}")
        traceback.print_exc()
        return 1
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        from chatterbox.tts import ChatterboxTTS
    except Exception as exc:
        emit_error(f"Chatterbox import failed: {exc}")
        traceback.print_exc()
        return 1

    device = args.device
    if device == "auto":
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"

    try:
        emit("loading_model")
        model = ChatterboxTTS.from_pretrained(device=device)
        emit("ready")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                emit_error("Invalid JSON request")
                continue
            cmd = req.get("cmd")
            if cmd == "shutdown":
                break
            if cmd != "synthesize":
                emit_error(f"Unknown command: {cmd}")
                continue
            ref_audio = Path(req.get("ref_audio", ""))
            output = Path(req.get("output", ""))
            text = req.get("text", "")
            if not ref_audio.is_file() or not text or not output:
                emit_error("synthesize requires ref_audio, text, and output")
                continue
            try:
                _synthesize_with_model(model, ref_audio, text, output)
            except Exception as exc:
                emit_error(f"Chatterbox synthesize failed: {exc}")
                traceback.print_exc()
    except Exception as exc:
        emit_error(f"Chatterbox serve failed: {exc}")
        traceback.print_exc()
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping")
    sub.add_parser("setup")

    p_synth = sub.add_parser("synthesize")
    p_synth.add_argument("--ref-audio", required=True)
    p_synth.add_argument("--text", required=True)
    p_synth.add_argument("--output", required=True)
    p_synth.add_argument("--device", default="auto")

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--device", default="auto")

    args = parser.parse_args()
    if args.command == "ping":
        return cmd_ping(args)
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "synthesize":
        return cmd_synthesize(args)
    if args.command == "serve":
        return cmd_serve(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
