import io


def test_transcribe_returns_text(client, silent_wav):
    r = client.post(
        "/transcribe",
        files={"file": ("test.wav", io.BytesIO(silent_wav), "audio/wav")},
    )
    assert r.status_code == 200
    body = r.json()
    assert "text" in body
    assert isinstance(body["text"], str)


def test_transcribe_language_field(client, silent_wav):
    r = client.post(
        "/transcribe",
        files={"file": ("test.wav", io.BytesIO(silent_wav), "audio/wav")},
    )
    body = r.json()
    assert "language" in body
