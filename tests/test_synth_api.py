from tests.test_voices_api import _create_voice, _wait_for_status


def _create_ready_voice(client):
    resp = _create_voice(client)
    voice = _wait_for_status(client, resp.json()["id"])
    assert voice["status"] == "ready"
    return voice


def test_synthesize_happy_path(client):
    voice = _create_ready_voice(client)
    resp = client.post(
        "/v1/synthesize",
        json={"voiceId": voice["id"], "text": "Hello world"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert len(resp.content) > 44  # bigger than just a WAV header


def test_synthesize_unknown_voice(client):
    resp = client.post("/v1/synthesize", json={"voiceId": "nope", "text": "hi"})
    assert resp.status_code == 404


def test_synthesize_not_ready_voice_conflicts(client):
    resp = _create_voice(client, engine_id="failing-engine")
    voice = _wait_for_status(client, resp.json()["id"])
    assert voice["status"] == "failed"

    synth_resp = client.post(
        "/v1/synthesize", json={"voiceId": voice["id"], "text": "hi"}
    )
    assert synth_resp.status_code == 409


def test_synthesize_text_too_long(client, settings):
    voice = _create_ready_voice(client)
    long_text = "a" * (settings.max_synth_chars + 1)
    resp = client.post(
        "/v1/synthesize", json={"voiceId": voice["id"], "text": long_text}
    )
    assert resp.status_code == 422
