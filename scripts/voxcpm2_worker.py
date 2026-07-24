#!/usr/bin/env python3
"""Isolated VoxCPM2 worker that accepts local model directories only."""

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


def cmd_synthesize(args: argparse.Namespace) -> int:
    model_dir = Path(args.model_dir)
    ref_audio = Path(args.ref_audio)
    output = Path(args.output)
    if not model_dir.is_dir() or not ref_audio.is_file():
        emit_error("VoxCPM2 requires existing local model-dir and reference audio paths")
        return 1
    try:
        from voxcpm import VoxCPM

        emit("loading_model", {"device": args.device})
        model = VoxCPM.from_pretrained(
            str(model_dir),
            load_denoiser=False,
            local_files_only=True,
            device=args.device,
        )
        target_text = args.text
        if args.style:
            target_text = f"({args.style.strip()}){target_text}"
        kwargs: dict = {
            "text": target_text,
            "reference_wav_path": str(ref_audio),
            "cfg_value": 2.0,
            "inference_timesteps": 10,
            "seed": args.seed,
        }
        if args.ref_text:
            kwargs["prompt_wav_path"] = str(ref_audio)
            kwargs["prompt_text"] = args.ref_text
        emit("synthesizing")
        wav = model.generate(**kwargs)

        import numpy as np
        import soundfile as sf

        if hasattr(wav, "detach"):
            array = wav.detach().cpu().numpy().astype("float32").squeeze()
        else:
            array = np.asarray(wav, dtype="float32").squeeze()
        sample_rate = int(getattr(getattr(model, "tts_model", None), "sample_rate", 48000))
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output), array, sample_rate, subtype="PCM_16")
        emit("done", {"output": str(output), "sample_rate": sample_rate})
        return 0
    except Exception as exc:
        emit_error(f"VoxCPM2 synthesis failed: {exc}")
        traceback.print_exc()
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ping")
    synth = sub.add_parser("synthesize")
    synth.add_argument("--model-dir", required=True)
    synth.add_argument("--ref-audio", required=True)
    synth.add_argument("--ref-text")
    synth.add_argument("--text", required=True)
    synth.add_argument("--style")
    synth.add_argument("--output", required=True)
    synth.add_argument("--device", default="auto")
    synth.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.command == "ping":
        return cmd_ping(args)
    if args.command == "synthesize":
        return cmd_synthesize(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
