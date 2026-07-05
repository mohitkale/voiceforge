def test_synth_applies_watermark_when_enabled(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "watermark_enabled", True)
    monkeypatch.setattr(settings, "watermark_strength", 0.01)

    import time

    from tests.conftest import FAKE_ENGINE_ID, make_wav_bytes

    files = [("files", ("sample.wav", make_wav_bytes(), "audio/wav"))]
    data = {
        "name": "WM Voice",
        "engine_id": FAKE_ENGINE_ID,
        "tier": "instant",
        "consent": "true",
        "language": "en",
    }
    created = client.post("/v1/voices", data=data, files=files)
    voice_id = created.json()["id"]
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        detail = client.get(f"/v1/voices/{voice_id}").json()
        if detail["status"] == "ready":
            break
        time.sleep(0.05)

    monkeypatch.setattr(settings, "watermark_enabled", False)
    synth_no_wm = client.post(
        "/v1/synthesize",
        json={"voiceId": voice_id, "text": "Plain synthesis."},
    )
    monkeypatch.setattr(settings, "watermark_enabled", True)
    synth_wm = client.post(
        "/v1/synthesize",
        json={"voiceId": voice_id, "text": "Plain synthesis."},
    )

    assert synth_wm.status_code == 200
    assert synth_no_wm.status_code == 200
    assert synth_wm.content != synth_no_wm.content
