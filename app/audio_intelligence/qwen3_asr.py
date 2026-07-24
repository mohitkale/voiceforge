"""Qwen3-ASR reference transcription through an isolated, local-only worker."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from app.audio_intelligence.base import AlignmentSegment, TranscriptionResult
from app.config import get_settings
from app.engines.base import EngineError
from app.engines.subprocess_env import sanitized_subprocess_env, worker_exec_command
from app.runtime_device import resolve_torch_device

_WORKER_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "qwen3_asr_worker.py"


class Qwen3AsrProvider:
    id = "qwen3-asr"

    def is_ready(self) -> bool:
        settings = get_settings()
        return (
            settings.qwen3_asr_python is not None
            and settings.qwen3_asr_python.is_file()
            and settings.qwen3_asr_model_dir is not None
            and settings.qwen3_asr_model_dir.is_dir()
            and _WORKER_SCRIPT.is_file()
        )

    def _invoke(self, args: list[str]) -> dict:
        settings = get_settings()
        python = settings.qwen3_asr_python
        if python is None or not python.is_file() or not self.is_ready():
            raise EngineError(
                "Qwen3-ASR is not configured; set VOICEFORGE_QWEN3_ASR_PYTHON "
                "and VOICEFORGE_QWEN3_ASR_MODEL_DIR to an isolated worker and "
                "an explicitly downloaded local snapshot"
            )

        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix="qwen3-asr-",
            suffix=".json",
            dir=settings.data_dir,
            delete=False,
        ) as tmp:
            output_path = Path(tmp.name)
        try:
            command = worker_exec_command(
                python,
                _WORKER_SCRIPT,
                [*args, "--output-json", str(output_path)],
            )
            proc = subprocess.run(  # noqa: S603 - argv contains validated local paths only
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
                env=sanitized_subprocess_env(),
            )
            if proc.returncode != 0:
                detail = (proc.stdout or proc.stderr or "worker failed").strip()
                raise EngineError(f"Qwen3-ASR worker failed: {detail[-1000:]}")
            return json.loads(output_path.read_text(encoding="utf-8"))
        except subprocess.TimeoutExpired as exc:
            raise EngineError("Qwen3-ASR worker timed out after 600 seconds") from exc
        finally:
            output_path.unlink(missing_ok=True)

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        timestamps: bool = False,
    ) -> TranscriptionResult:
        settings = get_settings()
        if not audio_path.is_file():
            raise EngineError(f"Reference audio not found: {audio_path}")
        assert settings.qwen3_asr_model_dir is not None
        args = [
            "transcribe",
            "--audio",
            str(audio_path),
            "--model-dir",
            str(settings.qwen3_asr_model_dir),
            "--device",
            resolve_torch_device(settings.device),
        ]
        if language:
            args.extend(["--language", language])
        if timestamps:
            aligner_dir = settings.qwen3_aligner_model_dir
            if aligner_dir is None or not aligner_dir.is_dir():
                raise EngineError(
                    "Qwen3-ASR timestamps require VOICEFORGE_QWEN3_ALIGNER_MODEL_DIR"
                )
            args.extend(["--timestamps", "--aligner-dir", str(aligner_dir)])
        return TranscriptionResult.model_validate(self._invoke(args))

    def align(
        self,
        audio_path: Path,
        *,
        text: str,
        language: str,
    ) -> list[AlignmentSegment]:
        settings = get_settings()
        aligner_dir = settings.qwen3_aligner_model_dir
        if aligner_dir is None or not aligner_dir.is_dir():
            raise EngineError(
                "Qwen3 forced alignment requires VOICEFORGE_QWEN3_ALIGNER_MODEL_DIR"
            )
        payload = self._invoke(
            [
                "align",
                "--audio",
                str(audio_path),
                "--text",
                text,
                "--language",
                language,
                "--aligner-dir",
                str(aligner_dir),
                "--device",
                resolve_torch_device(settings.device),
            ]
        )
        return [AlignmentSegment.model_validate(item) for item in payload["timestamps"]]
