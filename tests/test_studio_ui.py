def test_studio_ui_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert b"VoiceForge Studio" in resp.content
    assert b'id="consent"' in resp.content
    assert b"openvoice-v2" in resp.content
    assert b'fetch(path' in resp.content
    assert b"loadLanguages" in resp.content
    assert b"syncSynthLanguages" in resp.content
    assert b'<option value="en">en</option>' not in resp.content
    assert b'id="synthLanguage"' in resp.content
    assert b'id="synthStyle"' in resp.content
    assert b'style: $("synthStyle").value || null' in resp.content
