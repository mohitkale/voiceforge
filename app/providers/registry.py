"""Durable provider manifest registry.

Manifests are deliberately static and side-effect free: listing providers must
never import an ML SDK, contact a model hub, or start a worker.
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.providers.models import (
    LicenseMetadata,
    ModelPin,
    ProviderCapabilities,
    ProviderManifest,
    ProviderStatus,
    RuntimeSupport,
)

QWEN3_TTS_REVISION = "fd4b254"
CHATTERBOX_REVISION = "5bb1f6e"
QWEN3_ASR_REVISION = "5eb1441"
QWEN3_ALIGNER_REVISION = "c7cbfc2"
VOXCPM2_REVISION = "9454c2d"

_CH = ["ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja", "ko",
       "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh"]
_QWEN_TTS = ["en", "zh", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"]
_QWEN_ASR = [
    "ar", "cs", "da", "de", "el", "en", "es", "fa", "fi", "fil", "fr", "hi", "hu", "id",
    "it", "ja", "ko", "mk", "ms", "nl", "pl", "pt", "ro", "ru", "sv", "th", "tr", "vi",
    "yue", "zh",
]
_QWEN_ALIGN = ["zh", "en", "yue", "fr", "de", "it", "ja", "ko", "pt", "ru", "es"]
_VOXCPM2 = [
    "ar", "my", "zh", "da", "nl", "en", "fi", "fr", "de", "el", "he", "hi", "id", "it",
    "ja", "km", "ko", "lo", "ms", "no", "pl", "pt", "ru", "es", "sw", "sv", "tl", "th",
    "tr", "vi",
]


def _license(
    identifier: str,
    commercial: bool | None,
    url: str,
    *,
    gated: bool = False,
    notes: str | None = None,
) -> LicenseMetadata:
    return LicenseMetadata(
        identifier=identifier,
        commercial_use=commercial,
        gated=gated,
        source_url=url,
        notes=notes,
    )


def _runtime(
    mac: str,
    docker: str,
    notebook: str,
    preferred: str,
    notes: str | None = None,
) -> RuntimeSupport:
    return RuntimeSupport(
        mac_native=mac,
        docker_cpu=docker,
        cuda_notebook=notebook,
        preferred=preferred,
        notes=notes,
    )


_MANIFESTS = [
    ProviderManifest(
        id="xtts-v2",
        label="XTTS v2",
        kind="tts-clone",
        integration="integrated",
        default_enabled=True,
        explicit_opt_in=False,
        capabilities=ProviderCapabilities(
            languages=["en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs",
                       "ar", "zh", "ja", "hu", "ko", "hi"],
            text_to_speech=True,
            voice_clone=True,
        ),
        runtime=_runtime("experimental", "supported", "supported", "docker-cpu"),
        license=_license(
            "Coqui Public Model License",
            False,
            "https://huggingface.co/coqui/XTTS-v2",
            notes="Model-weight terms are noncommercial/research-oriented.",
        ),
        models=[ModelPin(model_id="tts_models/multilingual/multi-dataset/xtts_v2", revision=None)],
        dependency_file="requirements-xtts.txt",
    ),
    ProviderManifest(
        id="f5-tts",
        label="F5-TTS v1 Base",
        kind="tts-clone",
        integration="integrated",
        default_enabled=True,
        explicit_opt_in=False,
        capabilities=ProviderCapabilities(
            languages=["en", "zh"], text_to_speech=True, voice_clone=True
        ),
        runtime=_runtime("experimental", "supported", "supported", "cuda-notebook"),
        license=_license(
            "CC-BY-NC-4.0 weights",
            False,
            "https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/infer/SHARED.md",
            notes="Code and pretrained-weight licenses differ.",
        ),
        models=[ModelPin(model_id="SWivid/F5-TTS", revision=None)],
        dependency_file="requirements-f5.txt",
    ),
    ProviderManifest(
        id="openvoice-v2",
        label="OpenVoice V2",
        kind="tts-clone",
        integration="integrated",
        default_enabled=True,
        explicit_opt_in=False,
        capabilities=ProviderCapabilities(
            languages=["en", "es", "fr", "zh", "ja", "ko"],
            text_to_speech=True,
            voice_clone=True,
            voice_conversion=True,
        ),
        runtime=_runtime("experimental", "supported", "supported", "docker-cpu"),
        license=_license(
            "MIT adapter; base models separate",
            None,
            "https://github.com/myshell-ai/OpenVoice",
        ),
        dependency_file="requirements-openvoice.txt",
    ),
    ProviderManifest(
        id="rvc",
        label="RVC",
        kind="voice-conversion",
        integration="integrated",
        default_enabled=True,
        explicit_opt_in=False,
        capabilities=ProviderCapabilities(voice_conversion=True),
        runtime=_runtime("unsupported", "unsupported", "experimental", "worker"),
        license=_license(
            "MIT code; checkpoints/data separate",
            None,
            "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI",
        ),
        dependency_file="requirements-rvc.txt",
    ),
    ProviderManifest(
        id="chatterbox",
        label="Chatterbox Multilingual V3",
        kind="tts-clone",
        integration="integrated",
        default_enabled=True,
        explicit_opt_in=False,
        capabilities=ProviderCapabilities(
            languages=_CH,
            text_to_speech=True,
            voice_clone=True,
            expressive_control=True,
            code_switching=False,
        ),
        runtime=_runtime(
            "supported", "supported", "supported", "worker",
            "Mac native worker can use MPS; Docker Desktop is CPU-only.",
        ),
        license=_license(
            "MIT",
            True,
            "https://github.com/resemble-ai/chatterbox",
        ),
        models=[
            ModelPin(
                model_id="ResembleAI/chatterbox",
                revision=CHATTERBOX_REVISION,
                local_path_required=True,
            )
        ],
        dependency_file="requirements-chatterbox.txt",
    ),
    ProviderManifest(
        id="qwen3-tts",
        label="Qwen3-TTS 1.7B Base",
        kind="tts-clone",
        integration="integrated",
        default_enabled=True,
        explicit_opt_in=False,
        capabilities=ProviderCapabilities(
            languages=_QWEN_TTS,
            text_to_speech=True,
            voice_clone=True,
            expressive_control=True,
            code_switching=None,
        ),
        runtime=_runtime(
            "experimental", "experimental", "supported", "cuda-notebook",
            "MPS mapping is correct but upstream MPS quality/performance remains unverified.",
        ),
        license=_license(
            "Apache-2.0",
            True,
            "https://github.com/QwenLM/Qwen3-TTS",
        ),
        models=[
            ModelPin(
                model_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                revision=QWEN3_TTS_REVISION,
            )
        ],
        dependency_file="requirements-qwen3.txt",
    ),
    ProviderManifest(
        id="fish-speech",
        label="Fish Speech S2 sidecar",
        kind="tts-clone",
        integration="integrated",
        default_enabled=True,
        explicit_opt_in=False,
        capabilities=ProviderCapabilities(
            text_to_speech=True,
            voice_clone=True,
            expressive_control=True,
            languages=[],
        ),
        runtime=_runtime("unsupported", "experimental", "supported", "worker"),
        license=_license(
            "Fish Audio Research License",
            False,
            "https://github.com/fishaudio/fish-speech/blob/main/LICENSE",
            notes=(
                "Hindi is not advertised here because it was not verified "
                "from the primary source."
            ),
        ),
        dependency_file="requirements-fish.txt",
    ),
    ProviderManifest(
        id="cosyvoice-3",
        label="CosyVoice 3",
        kind="tts-clone",
        integration="integrated",
        default_enabled=True,
        explicit_opt_in=False,
        capabilities=ProviderCapabilities(
            languages=["zh", "en", "ja", "ko", "de", "es", "fr", "it", "ru"],
            text_to_speech=True,
            voice_clone=True,
            expressive_control=True,
        ),
        runtime=_runtime("unsupported", "experimental", "supported", "worker"),
        license=_license(
            "Apache-2.0",
            True,
            "https://github.com/QwenAudio/CosyVoice",
        ),
        dependency_file="requirements-cosyvoice.txt",
    ),
    ProviderManifest(
        id="indextts-2",
        label="IndexTTS2",
        kind="tts-clone",
        integration="integrated",
        default_enabled=True,
        explicit_opt_in=False,
        capabilities=ProviderCapabilities(
            languages=["en", "zh"],
            text_to_speech=True,
            voice_clone=True,
        ),
        runtime=_runtime("unsupported", "unsupported", "supported", "worker"),
        license=_license(
            "Bilibili IndexTTS Model License",
            None,
            "https://github.com/index-tts/index-tts/blob/main/LICENSE",
        ),
        dependency_file="requirements-indextts.txt",
    ),
    ProviderManifest(
        id="qwen3-asr",
        label="Qwen3-ASR 0.6B + optional Forced Aligner",
        kind="audio-intelligence",
        integration="experimental",
        default_enabled=False,
        explicit_opt_in=True,
        capabilities=ProviderCapabilities(
            languages=_QWEN_ASR,
            transcription=True,
            alignment=True,
            code_switching=None,
        ),
        runtime=_runtime(
            "experimental", "experimental", "supported", "worker",
            f"Forced alignment is limited to: {', '.join(_QWEN_ALIGN)}; it does not include Hindi.",
        ),
        license=_license(
            "Apache-2.0",
            True,
            "https://github.com/QwenLM/Qwen3-ASR",
        ),
        models=[
            ModelPin(
                model_id="Qwen/Qwen3-ASR-0.6B",
                revision=QWEN3_ASR_REVISION,
                local_path_required=True,
                purpose="transcription",
            ),
            ModelPin(
                model_id="Qwen/Qwen3-ForcedAligner-0.6B",
                revision=QWEN3_ALIGNER_REVISION,
                local_path_required=True,
                purpose="alignment",
            ),
        ],
        dependency_file="requirements-qwen3-asr.txt",
        notes=["Reference transcription backend only; no cloud API integration."],
    ),
    ProviderManifest(
        id="voxcpm2",
        label="VoxCPM2",
        kind="tts-clone",
        integration="experimental",
        default_enabled=False,
        explicit_opt_in=True,
        capabilities=ProviderCapabilities(
            languages=_VOXCPM2,
            text_to_speech=True,
            voice_clone=True,
            voice_design=True,
            expressive_control=True,
            code_switching=None,
        ),
        runtime=_runtime(
            "experimental", "experimental", "supported", "worker",
            "Upstream exposes MPS, but compatibility varies; Docker Desktop is CPU-only.",
        ),
        license=_license(
            "Apache-2.0",
            True,
            "https://github.com/OpenBMB/VoxCPM",
        ),
        models=[
            ModelPin(
                model_id="openbmb/VoxCPM2",
                revision=VOXCPM2_REVISION,
                local_path_required=True,
            )
        ],
        dependency_file="requirements-voxcpm2.txt",
    ),
    ProviderManifest(
        id="indicf5",
        label="AI4Bharat IndicF5 (license-gated experiment)",
        kind="tts-clone",
        integration="manifest-only",
        default_enabled=False,
        explicit_opt_in=True,
        capabilities=ProviderCapabilities(
            languages=["as", "bn", "gu", "hi", "kn", "ml", "mr", "or", "pa", "ta", "te"],
            text_to_speech=True,
            voice_clone=True,
        ),
        runtime=_runtime("unsupported", "unsupported", "experimental", "cuda-notebook"),
        license=_license(
            "MIT",
            True,
            "https://huggingface.co/ai4bharat/IndicF5",
            gated=True,
            notes=(
                "Access-gated; consent-only voice-cloning terms apply. No runtime "
                "integration because the upstream example executes remote model code."
            ),
        ),
        models=[ModelPin(model_id="ai4bharat/IndicF5", revision=None, local_path_required=True)],
        notes=["Manifest only; a reviewed, pinned local worker is required before enablement."],
    ),
    ProviderManifest(
        id="indic-parler-tts",
        label="AI4Bharat Indic Parler-TTS (license-gated experiment)",
        kind="tts",
        integration="manifest-only",
        default_enabled=False,
        explicit_opt_in=True,
        capabilities=ProviderCapabilities(
            languages=[
                "as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "kok", "mai", "ml", "mni",
                "mr", "ne", "or", "sa", "sat", "sd", "ta", "te", "ur",
            ],
            text_to_speech=True,
            voice_design=True,
            expressive_control=True,
        ),
        runtime=_runtime("unsupported", "unsupported", "experimental", "cuda-notebook"),
        license=_license(
            "Apache-2.0",
            True,
            "https://huggingface.co/ai4bharat/indic-parler-tts",
            gated=True,
            notes="Model files require accepting the upstream access gate.",
        ),
        models=[
            ModelPin(
                model_id="ai4bharat/indic-parler-tts",
                revision=None,
                local_path_required=True,
            )
        ],
        notes=["Manifest only; no startup install, remote code, or model access is attempted."],
    ),
]

_BY_ID = {manifest.id: manifest for manifest in _MANIFESTS}


def list_provider_manifests() -> list[ProviderManifest]:
    return list(_MANIFESTS)


def get_provider_manifest(provider_id: str) -> ProviderManifest:
    return _BY_ID[provider_id]


def _path_ready(path: Path | None) -> bool:
    return path is not None and path.is_dir()


def provider_statuses() -> list[ProviderStatus]:
    """Return status using filesystem/config checks only."""

    from app.engine_readiness import peek_engine_ready
    from app.engines.registry import engine_ids, is_engine_enabled

    settings = get_settings()
    engine_id_set = set(engine_ids())
    statuses: list[ProviderStatus] = []
    for manifest in _MANIFESTS:
        if manifest.id in engine_id_set:
            configured = is_engine_enabled(manifest.id)
            ready = configured and peek_engine_ready(manifest.id)
        elif manifest.id == "qwen3-asr":
            configured = settings.reference_asr_provider == "qwen3-asr"
            ready = (
                configured
                and settings.qwen3_asr_python is not None
                and settings.qwen3_asr_python.is_file()
                and _path_ready(settings.qwen3_asr_model_dir)
                and (Path(__file__).resolve().parents[2] / "scripts/qwen3_asr_worker.py").is_file()
            )
        else:
            configured = False
            ready = False
        statuses.append(ProviderStatus(manifest=manifest, configured=configured, ready=ready))
    return statuses
