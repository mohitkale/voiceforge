def test_metrics_endpoint(client):
    resp = client.get("/v1/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "uptimeSeconds" in body
    assert "synthRequests" in body
    assert "voicesCreated" in body
    assert body["uptimeSeconds"] >= 0


def test_metrics_increment_on_voice_create(client):
    before = client.get("/v1/metrics").json()["voicesCreated"]
    from tests.conftest import FAKE_ENGINE_ID, make_wav_bytes

    files = [("files", ("sample.wav", make_wav_bytes(), "audio/wav"))]
    data = {
        "name": "Metrics Voice",
        "engine_id": FAKE_ENGINE_ID,
        "tier": "instant",
        "consent": "true",
        "language": "en",
    }
    resp = client.post("/v1/voices", data=data, files=files)
    assert resp.status_code == 201
    after = client.get("/v1/metrics").json()["voicesCreated"]
    assert after == before + 1
