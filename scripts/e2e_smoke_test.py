#!/usr/bin/env python3
"""End-to-end smoke test against a running VoiceForge instance.

Uploads a generated reference clip, waits for clone completion, synthesizes
speech, and validates the output WAV header.

Usage (from a dev venv with httpx installed, service already running):
    python scripts/e2e_smoke_test.py --engine openvoice-v2
    python scripts/e2e_smoke_test.py --engine xtts-v2 --token "$VOICEFORGE_API_TOKEN"
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import wave
from pathlib import Path

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "httpx is required for this script — install dev deps: pip install -e '.[dev]'"
    ) from exc

# Long enough for F5/XTTS min_sample_seconds (6s) after preprocessing trim.
_SAMPLE_SECONDS = 6.5
_SAMPLE_RATE = 22050
_F5_REFERENCE_WAV = Path(__file__).resolve().parent / "fixtures" / "f5_reference_en.wav"


def _load_reference_wav(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) < 1000:
        raise RuntimeError(f"Reference WAV too small: {path}")
    return data


def _reference_bytes(engine_id: str, reference_wav: Path | None) -> bytes:
    if reference_wav is not None:
        return _load_reference_wav(reference_wav)
    # Engines that need intelligible speech for Whisper ref_text / ASR.
    if engine_id in {
        "f5-tts",
        "qwen3-tts",
        "fish-speech",
        "cosyvoice-3",
    }:
        if not _F5_REFERENCE_WAV.is_file():
            raise RuntimeError(
                f"{engine_id} needs intelligible speech for ref_text — "
                f"missing {_F5_REFERENCE_WAV}"
            )
        return _load_reference_wav(_F5_REFERENCE_WAV)
    return _generate_reference_wav()


def _generate_reference_wav() -> bytes:
    """Synthetic speech-like reference (formant mix + syllable envelope)."""
    import numpy as np

    t = np.linspace(0, _SAMPLE_SECONDS, int(_SAMPLE_RATE * _SAMPLE_SECONDS), endpoint=False)
    envelope = 0.55 + 0.45 * np.sin(2 * np.pi * 2.5 * t)
    wav = envelope * (
        0.35 * np.sin(2 * np.pi * 180 * t)
        + 0.30 * np.sin(2 * np.pi * 700 * t)
        + 0.20 * np.sin(2 * np.pi * 1100 * t)
        + 0.10 * np.sin(2 * np.pi * 2400 * t)
    )
    wav = (0.85 * wav / (np.max(np.abs(wav)) + 1e-9)).astype(np.float32)

    buf = io.BytesIO()
    import soundfile as sf

    sf.write(buf, wav, _SAMPLE_RATE, subtype="PCM_16", format="WAV")
    return buf.getvalue()


def _auth_headers(token: str | None) -> dict[str, str]:
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _validate_wav(data: bytes, min_bytes: int = 1000) -> None:
    if len(data) < min_bytes:
        raise RuntimeError(f"Output too small ({len(data)} bytes)")
    with wave.open(io.BytesIO(data), "rb") as wf:
        if wf.getnchannels() < 1:
            raise RuntimeError("WAV has no channels")
        if wf.getframerate() < 8000:
            raise RuntimeError(f"Unexpected sample rate: {wf.getframerate()}")
        frames = wf.readframes(wf.getnframes())
        if len(frames) < 100:
            raise RuntimeError("WAV contains almost no audio frames")
    # Sanity-check RIFF header without relying on wave for the prefix.
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RuntimeError("Response is not a RIFF WAVE file")


def run_smoke(
    *,
    base_url: str,
    engine_id: str,
    token: str | None,
    poll_timeout_s: float,
    poll_interval_s: float,
    out_path: Path | None,
    reference_wav: Path | None,
) -> None:
    base = base_url.rstrip("/")
    headers = _auth_headers(token)
    sample_bytes = _reference_bytes(engine_id, reference_wav)

    # CPU cold-start can block the host for minutes while multi-GB models load;
    # keep HTTP timeouts generous even though voice create returns quickly.
    timeout = httpx.Timeout(connect=30.0, read=600.0, write=120.0, pool=30.0)
    print(f"[1/4] Health check {base}/healthz")
    with httpx.Client(timeout=timeout) as client:
        health = client.get(f"{base}/healthz")
        health.raise_for_status()

        print(f"[2/4] Create voice (engine={engine_id})")
        create = client.post(
            f"{base}/v1/voices",
            headers=headers,
            data={
                "name": f"e2e-{engine_id}",
                "engine_id": engine_id,
                "tier": "instant",
                "consent": "true",
                "language": "en",
            },
            files={"files": ("reference.wav", sample_bytes, "audio/wav")},
        )
        if create.status_code >= 400:
            raise RuntimeError(f"Create voice failed ({create.status_code}): {create.text}")
        voice = create.json()
        voice_id = voice["id"]
        print(f"      voice_id={voice_id} status={voice['status']}")

        deadline = time.monotonic() + poll_timeout_s
        print(f"[3/4] Poll until ready (timeout={poll_timeout_s:.0f}s)")
        while True:
            detail = client.get(f"{base}/v1/voices/{voice_id}", headers=headers)
            detail.raise_for_status()
            body = detail.json()
            status = body["status"]
            if status == "ready":
                print("      status=ready")
                break
            if status == "failed":
                raise RuntimeError(f"Voice failed: {body.get('errorMessage') or body}")
            if time.monotonic() > deadline:
                raise RuntimeError(f"Timed out waiting for voice {voice_id} (last status={status})")
            time.sleep(poll_interval_s)

        print("[4/4] Synthesize")
        synth = client.post(
            f"{base}/v1/synthesize",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "voiceId": voice_id,
                "text": "Hello from VoiceForge end-to-end smoke test.",
                "language": "en",
            },
        )
        if synth.status_code >= 400:
            raise RuntimeError(f"Synthesize failed ({synth.status_code}): {synth.text}")

    wav_bytes = synth.content
    _validate_wav(wav_bytes)
    if out_path:
        out_path.write_bytes(wav_bytes)
        print(f"      wrote {out_path} ({len(wav_bytes)} bytes)")
    else:
        print(f"      valid WAV ({len(wav_bytes)} bytes)")
    print("PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8089")
    parser.add_argument("--engine", default="openvoice-v2")
    parser.add_argument("--token", default=None, help="Bearer token (or set VOICEFORGE_API_TOKEN)")
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=1800.0,
        help="Seconds to wait for clone",
    )
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--out", type=Path, default=None, help="Optional path to save synth WAV")
    parser.add_argument(
        "--reference-wav",
        type=Path,
        default=None,
        help=(
            "Reference clip to upload (default: synthetic; "
            "f5-tts / qwen3-tts / fish-speech / cosyvoice-3 use "
            "scripts/fixtures/f5_reference_en.wav)"
        ),
    )
    args = parser.parse_args()

    token = args.token
    if token is None:
        import os

        token = os.environ.get("VOICEFORGE_API_TOKEN") or None

    try:
        run_smoke(
            base_url=args.base_url,
            engine_id=args.engine,
            token=token,
            poll_timeout_s=args.poll_timeout,
            poll_interval_s=args.poll_interval,
            out_path=args.out,
            reference_wav=args.reference_wav,
        )
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
