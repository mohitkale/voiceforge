def test_studio_ui_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert b"VoiceForge Studio" in resp.content
