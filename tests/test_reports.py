import json

import pytest
from fastapi.testclient import TestClient

from observatory.api import create_app
from observatory.engine import run_experiment
from observatory.reports import compare_runs, export_csv, wilson


def test_pairing_exposes_regressions_and_improvements():
    stable = run_experiment(scenario="stable")
    bad = run_experiment()
    report = compare_runs(stable, bad)
    assert report["regressions"] == 5
    assert report["improvements"] == 0
    assert report["pass_rate_delta"] == -5 / 16
    assert sum(group["regressions"] for group in report["categories"].values()) == 5
    assert compare_runs(bad, stable)["improvements"] == 5
    assert wilson(0, 16)[0] == 0
    assert wilson(16, 16)[1] == 1
    assert wilson(8, 16)[0] < 0.5 < wilson(8, 16)[1]
    bad["dataset_sha256"] = "changed"
    with pytest.raises(ValueError, match="fingerprints"):
        compare_runs(stable, bad)


def test_csv_is_safe_for_spreadsheet_labels():
    run = run_experiment()
    run["traces"][0]["category"] = "=1+1"
    content = export_csv(run)
    assert "'=1+1" in content
    assert len(content.splitlines()) == 33


def test_dataset_upload_evaluate_compare_and_export(tmp_path):
    url = f"sqlite:///{tmp_path / 'datasets.db'}"
    case = {"id": "answer-1", "category": "reference", "prompt": "What is 2+2?",
            "baseline": "4", "candidate": "5", "checks": [{"type": "exact", "value": "4"}]}
    payload = {"name": "arithmetic-v1", "jsonl": json.dumps(case)}
    with TestClient(create_app(url)) as client:
        response = client.post("/api/datasets", json=payload)
        assert response.status_code == 201
        dataset = response.json()
        assert len(dataset["id"]) == 64
        assert "jsonl" not in dataset
        assert client.post("/api/datasets", json=payload).json() == dataset
        stable = client.post("/api/runs", json={
            "scenario": "stable", "dataset_id": dataset["id"],
        }).json()
        bad = client.post("/api/runs", json={"dataset_id": dataset["id"]}).json()
        compared = client.get("/api/compare", params={
            "baseline": stable["id"], "candidate": bad["id"],
        }).json()
        assert compared["regressions"] == 1
        csv = client.get(f'/api/runs/{bad["id"]}/export?format=csv')
        assert csv.status_code == 200 and "text/csv" in csv.headers["content-type"]
        assert "attachment" in csv.headers["content-disposition"]
        assert client.get(f'/api/runs/{bad["id"]}/export').json() == bad
        builtin = client.post("/api/runs", json={}).json()
        assert client.get("/api/compare", params={
            "baseline": stable["id"], "candidate": builtin["id"],
        }).status_code == 409
        assert client.post("/api/runs", json={"dataset_id": "f" * 64}).status_code == 404
        assert client.post("/api/datasets", json={
            "name": "bad", "jsonl": '{"PRIVATE-MARKER":true}',
        }).status_code == 422
    with TestClient(create_app(url)) as client:
        assert client.get("/api/datasets").json()[1] == dataset
        assert len(client.get("/api/runs").json()) == 3
