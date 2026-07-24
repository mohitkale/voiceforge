"""Pure device-selection helpers shared by in-process and worker providers."""

from __future__ import annotations

from typing import Any

VALID_DEVICES = {"auto", "cpu", "cuda", "mps"}


def resolve_torch_device(requested: str, torch_module: Any | None = None) -> str:
    """Resolve ``auto`` with CUDA first, then Apple MPS, then CPU.

    Explicit values are preserved so workers can produce a useful SDK-level
    error. This helper never imports torch unless automatic detection is
    requested.
    """

    normalized = (requested or "auto").lower()
    if normalized not in VALID_DEVICES:
        expected = sorted(VALID_DEVICES)
        raise ValueError(f"Unsupported device '{requested}'; expected one of {expected}")
    if normalized != "auto":
        return normalized

    if torch_module is None:
        try:
            import torch as torch_module
        except Exception:
            return "cpu"

    if torch_module.cuda.is_available():
        return "cuda"
    mps = getattr(getattr(torch_module, "backends", None), "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


def transformers_device_map(device: str) -> str:
    """Return a valid Transformers ``device_map`` target."""

    if device == "cuda":
        return "cuda:0"
    if device in {"cpu", "mps"}:
        return device
    raise ValueError(f"Device must be resolved before building device_map: {device}")
