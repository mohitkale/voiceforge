#!/usr/bin/env python3
"""Isolated RVC worker — runs in a separate venv from the main VoiceForge app.

Emits JSON progress lines on stdout for the parent process to forward over SSE.

Commands:
    ping
    setup
    train --work-dir DIR --model-name NAME --samples FILE [FILE ...]
    infer --model PATH --input PATH --output PATH [--index PATH]
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
    emit("downloading_base_models")
    try:
        import rvc_python
        from rvc_python.download_model import download_rvc_models

        lib_dir = Path(rvc_python.__file__).resolve().parent
        download_rvc_models(str(lib_dir))
    except Exception as exc:
        emit_error(f"RVC setup failed: {exc}")
        traceback.print_exc()
        return 1
    emit("setup_complete")
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    samples = [Path(p) for p in args.samples]
    for sample in samples:
        if not sample.is_file():
            emit_error(f"Sample not found: {sample}")
            return 1

    emit("training_start", {"epochs": args.epochs, "model": args.model_name})

    try:
        from config import PipelineConfig
        from pipeline import RVCPipeline
    except ImportError:
        emit_error(
            "rvc-no-gui is not installed in this venv — "
            "pip install git+https://github.com/nakshatra-garg/rvc-no-gui.git"
        )
        return 1

    cfg = PipelineConfig()
    cfg.paths.base_dir = work_dir
    cfg.paths.models_dir = work_dir / "rvc_models"
    cfg.paths.datasets_dir = work_dir / "datasets"
    cfg.training.epochs = args.epochs
    cfg.training.batch_size = args.batch_size
    if args.device.startswith("cuda"):
        cfg.training.gpu_id = "0"

    pipeline = RVCPipeline(cfg)

    if not args.skip_setup:
        emit("rvc_setup")
        if not pipeline.run_setup():
            emit_error("RVC environment setup failed")
            return 1

    emit("preparing_dataset")
    if not pipeline.dataset.prepare_dataset(
        audio_files=samples,
        model_name=args.model_name,
    ):
        emit_error("Dataset preparation failed")
        return 1

    emit("training_model", {"epochs": args.epochs})
    ok = pipeline.trainer.train(model_name=args.model_name)

    if not ok:
        emit_error("RVC training failed")
        return 1

    weights = cfg.paths.get_model_weights_path(args.model_name)
    emit("training_complete", {"weights": str(weights)})
    return 0


def cmd_infer(args: argparse.Namespace) -> int:
    model_path = Path(args.model)
    input_path = Path(args.input)
    output_path = Path(args.output)
    if not model_path.is_file():
        emit_error(f"Model not found: {model_path}")
        return 1
    if not input_path.is_file():
        emit_error(f"Input not found: {input_path}")
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)

    emit("loading_model")
    try:
        from rvc_python.infer import RVCInference
    except ImportError as exc:
        emit_error(f"rvc-python not installed: {exc}")
        return 1

    index_path = args.index or ""
    rvc = RVCInference(
        device=args.device,
        model_path=str(model_path),
        index_path=index_path,
        version=args.version,
    )
    rvc.set_params(f0method="rmvpe")
    emit("inferring")
    rvc.infer_file(str(input_path), str(output_path))
    emit("infer_complete", {"output": str(output_path)})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping")

    sub.add_parser("setup")

    train_p = sub.add_parser("train")
    train_p.add_argument("--work-dir", required=True)
    train_p.add_argument("--model-name", required=True)
    train_p.add_argument("--samples", nargs="+", required=True)
    train_p.add_argument("--epochs", type=int, default=50)
    train_p.add_argument("--batch-size", type=int, default=4)
    train_p.add_argument("--device", default="cpu")
    train_p.add_argument("--skip-setup", action="store_true")

    infer_p = sub.add_parser("infer")
    infer_p.add_argument("--model", required=True)
    infer_p.add_argument("--input", required=True)
    infer_p.add_argument("--output", required=True)
    infer_p.add_argument("--index", default="")
    infer_p.add_argument("--device", default="cpu:0")
    infer_p.add_argument("--version", default="v2", choices=["v1", "v2"])

    args = parser.parse_args()
    handlers = {
        "ping": cmd_ping,
        "setup": cmd_setup,
        "train": cmd_train,
        "infer": cmd_infer,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
