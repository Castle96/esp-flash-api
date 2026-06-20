def test_chat_returns_reply(client):
    r = client.post("/chat", json={"text": "turn on the lab lights"})
    assert r.status_code == 200
    body = r.json()
    assert "reply" in body
    assert len(body["reply"]) > 0


def test_chat_with_session_id(client):
    r = client.post("/chat", json={"text": "status report", "session_id": "test-001"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "test-001"
