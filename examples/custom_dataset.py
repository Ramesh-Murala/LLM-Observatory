"""Exercise custom dataset upload, paired runs, comparison, and evidence exports."""

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "reports"
    output.mkdir(exist_ok=True)
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=60, trust_env=False) as client:
        response = client.post("/api/datasets", json={
            "name": "structured-contracts-v1",
            "jsonl": (ROOT / "observatory/data/structured-contracts-v1.jsonl").read_text(),
        })
        response.raise_for_status()
        dataset = response.json()
        runs = {}
        for scenario in ("stable", "regression"):
            response = client.post("/api/runs", json={
                "scenario": scenario, "dataset_id": dataset["id"],
            })
            response.raise_for_status()
            runs[scenario] = response.json()
            (output / f"schema-{scenario}.json").write_text(
                json.dumps(response.json(), indent=2), encoding="utf-8"
            )
        response = client.get("/api/compare", params={
            "baseline": runs["stable"]["id"], "candidate": runs["regression"]["id"],
        })
        response.raise_for_status()
        report = response.json()
        (output / "schema-comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        response = client.get(f'/api/runs/{runs["regression"]["id"]}/export?format=csv')
        response.raise_for_status()
        (output / "schema-regression.csv").write_text(response.text, encoding="utf-8")
        print(json.dumps({"dataset_cases": dataset["cases"], "regressions": report["regressions"],
                          "stable_passed": runs["stable"]["gate"]["passed"],
                          "regression_blocked": not runs["regression"]["gate"]["passed"]}, indent=2))


if __name__ == "__main__":
    main()
