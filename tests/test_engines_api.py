from tests.conftest import FAKE_ENGINE_ID


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
