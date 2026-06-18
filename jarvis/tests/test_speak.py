def test_speak_returns_wav(client):
    r = client.post("/speak", json={"text": "Understood. Lab lights are on."})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF"


def test_speak_non_empty(client):
    r = client.post("/speak", json={"text": "Working on it."})
    assert r.status_code == 200
    assert len(r.content) > 44
