import time

from tests.conftest import FAKE_ENGINE_ID, make_wav_bytes


def _wait_for_status(client, voice_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        resp = client.get(f"/v1/voices/{voice_id}")
        last = resp.json()
        if last["status"] in ("ready", "failed"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"Voice never reached a terminal status: {last}")


def _create_voice(client, *, engine_id=FAKE_ENGINE_ID, consent=True, tier="instant", n_files=1):
    files = [
        ("files", (f"sample{i}.wav", make_wav_bytes(), "audio/wav")) for i in range(n_files)
    ]
    data = {
        "name": "Test Voice",
        "engine_id": engine_id,
        "tier": tier,
        "consent": str(consent).lower(),
        "language": "en",
    }
    return client.post("/v1/voices", data=data, files=files)


def test_create_voice_happy_path(client):
    resp = _create_voice(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] in ("processing", "ready")
    assert body["sampleCount"] == 1

    final = _wait_for_status(client, body["id"])
    assert final["status"] == "ready"
    assert final["readyAt"] is not None


def test_create_voice_requires_consent(client):
    resp = _create_voice(client, consent=False)
    assert resp.status_code == 422


def test_create_voice_unknown_engine(client):
    resp = _create_voice(client, engine_id="does-not-exist")
    assert resp.status_code == 404


def test_create_voice_rejects_non_audio(client):
    data = {
        "name": "Bad Voice",
        "engine_id": FAKE_ENGINE_ID,
        "tier": "instant",
        "consent": "true",
        "language": "en",
    }
    files = [("files", ("not-audio.wav", b"this is not audio data", "audio/wav"))]
    resp = client.post("/v1/voices", data=data, files=files)
    assert resp.status_code == 422


def test_create_voice_too_many_samples(client, settings):
    n = settings.max_samples_per_voice + 1
    resp = _create_voice(client, n_files=n)
    assert resp.status_code == 422


def test_create_voice_failure_marks_failed(client):
    resp = _create_voice(client, engine_id="failing-engine")
    assert resp.status_code == 201
    final = _wait_for_status(client, resp.json()["id"])
    assert final["status"] == "failed"
    assert final["errorMessage"]


def test_list_and_get_and_delete_voice(client):
    created = _create_voice(client).json()
    voice_id = created["id"]

    listed = client.get("/v1/voices").json()
    assert any(v["id"] == voice_id for v in listed)

    detail = client.get(f"/v1/voices/{voice_id}")
    assert detail.status_code == 200

    deleted = client.delete(f"/v1/voices/{voice_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/v1/voices/{voice_id}")
    assert missing.status_code == 404


def test_get_voice_not_found(client):
    resp = client.get("/v1/voices/does-not-exist")
    assert resp.status_code == 404
