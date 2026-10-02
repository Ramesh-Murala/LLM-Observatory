import json

import pytest

from observatory.engine import gate, load_dataset, run_experiment
from observatory.providers import FixtureProvider


def summary(rate=1, latency=100, errors=0):
    return {"pass_rate": rate, "p95_ms": latency, "errors": errors}


def test_threshold_is_inclusive():
    assert gate(summary(), summary(0.98, 150))["passed"]
    assert not gate(summary(), summary(0.97, 150))["passed"]
    assert not gate(summary(), summary(1, 151))["passed"]
    assert not gate(summary(), summary(1, 100, 1))["passed"]


def test_fixture_regression_is_reproducible():
    run = run_experiment()
    assert run["summaries"]["baseline"]["pass_rate"] == 1
    assert run["summaries"]["candidate"]["pass_rate"] == 11 / 16
    assert not run["gate"]["passed"]
    assert len(run["traces"]) == 32
    assert len({row["id"] for row in run["traces"]}) == 32
    assert all(row["trace_id"] != "0" * 32 for row in run["traces"])
    assert len({row["span_id"] for row in run["traces"]}) == 32
    assert all(row["latency_source"] == "simulated" for row in run["traces"])


def test_stable_fixture_passes():
    assert run_experiment(scenario="stable")["gate"]["passed"]


def test_provider_failure_becomes_failed_evidence(monkeypatch):
    def fail(*args):
        raise TimeoutError("credential-marker-XYZ must not be saved")

    monkeypatch.setattr(FixtureProvider, "complete", fail)
    run = run_experiment()
    assert run["summaries"]["candidate"]["errors"] == 16
    assert not run["gate"]["passed"]
    assert run["traces"][0]["error"] == "TimeoutError"
    assert "credential-marker-XYZ" not in json.dumps(run)


def test_duplicate_ids_are_rejected(tmp_path):
    cases, _ = load_dataset()
    path = tmp_path / "invalid.jsonl"
    path.write_text("\n".join(json.dumps(cases[0]) for _ in range(2)))
    with pytest.raises(ValueError, match="unique"):
        load_dataset(path)


def test_remote_cost_uses_supplied_rates(monkeypatch):
    from observatory.providers import CompatibleProvider, Completion

    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    for variant in ("BASELINE", "CANDIDATE"):
        monkeypatch.setenv(f"LLM_{variant}_INPUT_USD_PER_MILLION", "2")
        monkeypatch.setenv(f"LLM_{variant}_OUTPUT_USD_PER_MILLION", "4")
    monkeypatch.setattr(
        CompatibleProvider,
        "complete",
        lambda self, case, variant: Completion(case["baseline"], 100, 50, "provider"),
    )
    run = run_experiment(provider_name="compatible")
    assert run["summaries"]["candidate"]["estimated_cost_usd"] == pytest.approx(0.0064)
    assert all(row["latency_source"] == "measured" for row in run["traces"])


def test_unknown_cost_is_not_reported_as_zero(monkeypatch):
    from observatory.providers import CompatibleProvider, Completion

    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    for variant in ("BASELINE", "CANDIDATE"):
        monkeypatch.delenv(f"LLM_{variant}_INPUT_USD_PER_MILLION", raising=False)
        monkeypatch.delenv(f"LLM_{variant}_OUTPUT_USD_PER_MILLION", raising=False)
    monkeypatch.setattr(
        CompatibleProvider,
        "complete",
        lambda self, case, variant: Completion(case["baseline"], 0, 0, "unavailable"),
    )
    assert (
        run_experiment(provider_name="compatible")["summaries"]["candidate"]["estimated_cost_usd"]
        is None
    )
