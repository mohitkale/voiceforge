"""Structured, API-safe metadata for local model providers.

The engine protocol intentionally stays small. These manifests describe the
operational facts that do not belong in ``CloneCapabilities``: immutable model
revisions, license gates, integration maturity, and platform-specific runtime
support.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProviderKind = Literal["tts-clone", "voice-conversion", "audio-intelligence", "tts"]
IntegrationState = Literal["integrated", "experimental", "manifest-only"]
SupportLevel = Literal["supported", "experimental", "unsupported"]


class ModelPin(BaseModel):
    model_id: str
    revision: str | None
    local_path_required: bool = False
    purpose: str = "inference"


class LicenseMetadata(BaseModel):
    identifier: str
    commercial_use: bool | None
    gated: bool = False
    source_url: str
    notes: str | None = None


class RuntimeSupport(BaseModel):
    mac_native: SupportLevel
    docker_cpu: SupportLevel
    cuda_notebook: SupportLevel
    preferred: Literal["mac-native", "docker-cpu", "cuda-notebook", "worker"]
    notes: str | None = None


class ProviderCapabilities(BaseModel):
    languages: list[str] = Field(default_factory=list)
    text_to_speech: bool = False
    voice_clone: bool = False
    voice_design: bool = False
    expressive_control: bool = False
    voice_conversion: bool = False
    transcription: bool = False
    alignment: bool = False
    code_switching: bool | None = None


class ProviderManifest(BaseModel):
    id: str
    label: str
    kind: ProviderKind
    integration: IntegrationState
    default_enabled: bool
    explicit_opt_in: bool
    local_only: bool = True
    capabilities: ProviderCapabilities
    runtime: RuntimeSupport
    license: LicenseMetadata
    models: list[ModelPin] = Field(default_factory=list)
    dependency_file: str | None = None
    notes: list[str] = Field(default_factory=list)


class ProviderStatus(BaseModel):
    manifest: ProviderManifest
    configured: bool
    ready: bool

