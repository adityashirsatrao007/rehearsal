"""HTTP-level tests. None of these touch the model, so they stay fast."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_serves_html():
    res = client.get("/")
    assert res.status_code == 200
    assert "Rehearsal" in res.text


def test_static_assets_are_served():
    for path in ("/static/app.js", "/static/styles.css"):
        assert client.get(path).status_code == 200


def test_scenarios_endpoint_returns_the_full_set():
    res = client.get("/api/scenarios")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 5
    for s in data:
        assert set(s) == {"id", "title", "emoji", "blurb", "opening"}


def test_status_reports_ollama_state():
    res = client.get("/api/status")
    assert res.status_code == 200
    assert set(res.json()) >= {"ready", "ollama", "model", "models", "detail"}


def test_progress_starts_empty():
    res = client.get("/api/progress")
    assert res.status_code == 200
    assert res.json()["sessions_completed"] == 0


def test_create_session_rejects_unknown_scenario():
    res = client.post("/api/sessions", json={"scenario": "nonsense"})
    assert res.status_code == 404


def test_session_lifecycle():
    created = client.post("/api/sessions", json={"scenario": "interview"})
    assert created.status_code == 200
    session = created.json()
    assert session["scenario"] == "interview"

    fetched = client.get(f"/api/sessions/{session['id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["messages"] == []
    assert body["corrections"] == []

    deleted = client.delete(f"/api/sessions/{session['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/sessions/{session['id']}").status_code == 404


def test_missing_session_returns_404():
    assert client.get("/api/sessions/999999").status_code == 404
    assert client.delete("/api/sessions/999999").status_code == 404


def test_summary_refuses_an_empty_session_before_calling_the_model():
    session = client.post("/api/sessions", json={"scenario": "smalltalk"}).json()
    res = client.post(f"/api/sessions/{session['id']}/summary")
    assert res.status_code == 409
    assert "send a message first" in res.json()["detail"]


def test_message_rejects_blank_content():
    session = client.post("/api/sessions", json={"scenario": "client"}).json()
    res = client.post(f"/api/sessions/{session['id']}/messages", json={"content": ""})
    assert res.status_code == 422
