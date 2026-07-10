from app.config import get_settings
from app.engines import registry as engine_registry


def test_enabled_engines_lists_all_but_marks_configured(client, monkeypatch):
    monkeypatch.setenv(
        "VOICEFORGE_ENABLED_ENGINES",
        "qwen3-tts,chatterbox,fake-engine",
    )
    get_settings.cache_clear()
    engine_registry._instances.clear()

    resp = client.get("/v1/engines")
    engines = resp.json()
    ids = {e["id"] for e in engines}
    assert "fish-speech" in ids
    assert "cosyvoice-3" in ids
    assert len(ids) >= 9

    fish = next(e for e in engines if e["id"] == "fish-speech")
    assert fish["configured"] is False
    assert fish["ready"] is False

    qwen = next(e for e in engines if e["id"] == "qwen3-tts")
    assert qwen["configured"] is True

    get_settings.cache_clear()
    engine_registry._instances.clear()
    monkeypatch.delenv("VOICEFORGE_ENABLED_ENGINES", raising=False)
