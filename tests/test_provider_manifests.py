from app.providers.registry import get_provider_manifest, list_provider_manifests


def test_provider_manifest_ids_and_opt_in_contracts():
    manifests = {manifest.id: manifest for manifest in list_provider_manifests()}
    assert {"qwen3-asr", "voxcpm2", "indicf5", "indic-parler-tts"} <= set(manifests)
    assert manifests["voxcpm2"].default_enabled is False
    assert manifests["voxcpm2"].explicit_opt_in is True
    assert manifests["qwen3-asr"].default_enabled is False
    assert manifests["indicf5"].integration == "manifest-only"
    assert manifests["indic-parler-tts"].integration == "manifest-only"
    assert manifests["indicf5"].license.gated is True
    assert manifests["indicf5"].license.identifier == "MIT"
    assert manifests["indic-parler-tts"].license.identifier == "Apache-2.0"
    assert "pa" not in manifests["indic-parler-tts"].capabilities.languages


def test_experimental_model_revisions_are_immutable_and_local_only():
    for provider_id in ("qwen3-asr", "voxcpm2"):
        manifest = get_provider_manifest(provider_id)
        assert manifest.models
        for model in manifest.models:
            assert model.local_path_required is True
            assert model.revision not in (None, "", "main", "latest")


def test_verified_hindi_and_alignment_metadata():
    qwen_asr = get_provider_manifest("qwen3-asr")
    assert "hi" in qwen_asr.capabilities.languages
    assert qwen_asr.capabilities.transcription is True
    assert qwen_asr.capabilities.alignment is True
    assert "does not include Hindi" in (qwen_asr.runtime.notes or "")

    voxcpm2 = get_provider_manifest("voxcpm2")
    assert "hi" in voxcpm2.capabilities.languages
    assert voxcpm2.capabilities.voice_clone is True
    assert voxcpm2.capabilities.voice_design is True


def test_provider_api_is_side_effect_free(client):
    response = client.get("/v1/providers")
    assert response.status_code == 200
    statuses = {item["manifest"]["id"]: item for item in response.json()}
    assert statuses["voxcpm2"]["configured"] is False
    assert statuses["voxcpm2"]["ready"] is False
    assert statuses["indicf5"]["configured"] is False
