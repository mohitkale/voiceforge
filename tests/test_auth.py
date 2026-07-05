def test_v1_route_open_when_no_token_configured(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "api_token", None)
    resp = client.get("/v1/engines")
    assert resp.status_code == 200


def test_v1_route_rejects_missing_token(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "api_token", "super-secret-token")
    resp = client.get("/v1/engines")
    assert resp.status_code == 401


def test_v1_route_rejects_wrong_token(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "api_token", "super-secret-token")
    resp = client.get("/v1/engines", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


def test_v1_route_accepts_correct_token(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "api_token", "super-secret-token")
    resp = client.get("/v1/engines", headers={"Authorization": "Bearer super-secret-token"})
    assert resp.status_code == 200
