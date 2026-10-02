from fastapi.testclient import TestClient

from observatory.api import create_app


def test_full_run_and_persistence(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    with TestClient(create_app(url)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/runs").json() == []
        response = client.post("/api/runs", json={"scenario": "regression"})
        assert response.status_code == 201
        run = response.json()
        assert not run["gate"]["passed"]
        assert client.get(f"/api/runs/{run['id']}").json() == run
        assert "traces" not in client.get("/api/runs").json()[0]
        assert "observatory_retained_failed_cases 5" in client.get("/metrics").text
        assert client.post("/api/runs", json={"scenario": "bad"}).status_code == 422
        assert client.get("/api/runs/missing").status_code == 404
        assert client.get("/").status_code == 200
    with TestClient(create_app(url)) as client:
        assert len(client.get("/api/runs").json()) == 1


def test_browser_runs_never_use_paid_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "unused")
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        run = client.post("/api/runs", json={"scenario": "stable"}).json()
        assert run["provider"] == "fixture"
        assert run["gate"]["passed"]
