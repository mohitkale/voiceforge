def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "voiceforge"
    assert body["version"] == "0.3.0"
    assert body["enginesTotal"] >= 4
    assert "enginesReady" in body


def test_healthz_requires_no_auth(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "api_token", "some-secret")
    resp = client.get("/healthz")
    assert resp.status_code == 200
