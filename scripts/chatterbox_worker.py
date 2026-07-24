#!/usr/bin/env python3
"""Isolated Chatterbox worker — separate venv (numpy<2 / torch pins).

Commands:
    ping
    setup
    synthesize --model-dir PATH --ref-audio PATH --text TEXT --language en
               --output PATH [--device cpu|cuda|mps]
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
    model_dir = Path(_args.model_dir)
    emit("downloading_chatterbox", {"revision": _args.revision})
    try:
        from huggingface_hub import snapshot_download

        model_dir.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id="ResembleAI/chatterbox",
            revision=_args.revision,
            local_dir=str(model_dir),
        )
        emit("setup_complete", {"model_dir": str(model_dir)})
    except Exception as exc:
        emit_error(f"Chatterbox setup failed: {exc}")
        traceback.print_exc()
        return 1
    return 0


def _synthesize_with_model(
    model,
    ref_audio: Path,
    text: str,
    output: Path,
    language: str,
) -> None:
    import numpy as np
    import soundfile as sf

    emit("synthesizing")
    wav = model.generate(
        text,
        language_id=language,
        audio_prompt_path=str(ref_audio),
    )
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
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
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

                if torch.cuda.is_available():
                    device = "cuda"
                elif torch.backends.mps.is_available():
                    device = "mps"
                else:
                    device = "cpu"
            except Exception:
                device = "cpu"
        model = ChatterboxMultilingualTTS.from_local(
            args.model_dir,
            device=device,
            t3_model=args.t3_model,
        )
        _synthesize_with_model(model, ref_audio, args.text, output, args.language)
    except Exception as exc:
        emit_error(f"Chatterbox synthesize failed: {exc}")
        traceback.print_exc()
        return 1
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    except Exception as exc:
        emit_error(f"Chatterbox import failed: {exc}")
        traceback.print_exc()
        return 1

    device = args.device
    if device == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        except Exception:
            device = "cpu"

    try:
        emit("loading_model")
        model = ChatterboxMultilingualTTS.from_local(
            args.model_dir,
            device=device,
            t3_model=args.t3_model,
        )
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
            language = req.get("language", "")
            if not ref_audio.is_file() or not text or not output or not language:
                emit_error("synthesize requires ref_audio, text, output, and language")
                continue
            try:
                _synthesize_with_model(model, ref_audio, text, output, language)
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
    p_setup = sub.add_parser("setup")
    p_setup.add_argument("--model-dir", required=True)
    p_setup.add_argument("--revision", required=True)

    p_synth = sub.add_parser("synthesize")
    p_synth.add_argument("--ref-audio", required=True)
    p_synth.add_argument("--text", required=True)
    p_synth.add_argument("--output", required=True)
    p_synth.add_argument("--language", required=True)
    p_synth.add_argument("--device", default="auto")
    p_synth.add_argument("--model-dir", required=True)
    p_synth.add_argument("--t3-model", default="v3")

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--device", default="auto")
    p_serve.add_argument("--model-dir", required=True)
    p_serve.add_argument("--t3-model", default="v3")

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
