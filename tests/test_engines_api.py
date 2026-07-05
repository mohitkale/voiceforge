from tests.conftest import FAKE_ENGINE_ID


def test_list_engines_includes_built_in_ids(client):
    resp = client.get("/v1/engines")
    ids = {e["id"] for e in resp.json()}
    assert "xtts-v2" in ids
    assert "f5-tts" in ids
    assert "openvoice-v2" in ids
    assert "rvc" in ids


def test_openvoice_engine_metadata(client):
    resp = client.get("/v1/engines")
    ov = next(e for e in resp.json() if e["id"] == "openvoice-v2")
    assert ov["label"].startswith("OpenVoice V2")
    assert ov["capabilities"]["zero_shot"] is True
    assert "MIT" in ov["capabilities"]["license"]
    assert "ko" in ov["capabilities"]["languages"]


def test_f5_engine_metadata(client):
    resp = client.get("/v1/engines")
    f5 = next(e for e in resp.json() if e["id"] == "f5-tts")
    assert f5["label"].startswith("F5-TTS")
    assert f5["capabilities"]["zero_shot"] is True
    assert "Apache" in f5["capabilities"]["license"]


def test_rvc_engine_metadata(client):
    resp = client.get("/v1/engines")
    rvc = next(e for e in resp.json() if e["id"] == "rvc")
    assert rvc["label"].startswith("RVC")
    assert rvc["capabilities"]["fine_tunable"] is True
    assert rvc["capabilities"]["zero_shot"] is False
    assert rvc["capabilities"]["requires_gpu"] is True


def test_list_engines_includes_fake_engine(client):
    resp = client.get("/v1/engines")
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert FAKE_ENGINE_ID in ids


def test_engine_shape(client):
    resp = client.get("/v1/engines")
    fake = next(e for e in resp.json() if e["id"] == FAKE_ENGINE_ID)
    assert fake["ready"] is True
    assert fake["configured"] is True
    assert "capabilities" in fake
    assert fake["capabilities"]["license"] == "MIT"
