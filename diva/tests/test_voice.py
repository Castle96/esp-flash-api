import io


def test_voice_full_pipeline(client, silent_wav):
    """
    Full round-trip: audio in -> STT -> LLM -> TTS -> WAV out.
    All three stages are mocked; no hardware or network required.
    """
    r = client.post(
        "/voice",
        files={"file": ("audio.raw", io.BytesIO(silent_wav), "audio/wav")},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF"
    assert len(r.content) > 44


def test_voice_returns_wav_on_speech(client, silent_wav):
    r = client.post(
        "/voice",
        files={"file": ("audio.raw", io.BytesIO(silent_wav), "audio/octet-stream")},
    )
    assert r.status_code == 200
    assert r.content[:4] == b"RIFF"


def test_history_cleared(client):
    r = client.delete("/history")
    assert r.status_code == 200
    assert r.json()["ok"] is True
