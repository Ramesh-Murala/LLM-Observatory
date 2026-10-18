import json
import subprocess
import sys

import pytest


@pytest.mark.parametrize("scenario,expected", [("stable", 0), ("regression", 1)])
def test_gate_exit_code_and_report(tmp_path, scenario, expected):
    report = tmp_path / "gate.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "observatory.cli",
            "gate",
            "--scenario",
            scenario,
            "--output",
            str(report),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected
    assert json.loads(report.read_text())["gate"]["passed"] == (expected == 0)


def test_missing_dataset_is_execution_error(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "observatory.cli",
            "gate",
            "--dataset",
            str(tmp_path / "missing.jsonl"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_structured_suite_and_comparison_cli(tmp_path):
    reports = {}
    for scenario, expected in (("stable", 0), ("regression", 1)):
        path = tmp_path / f"{scenario}.json"
        result = subprocess.run([
            sys.executable, "-m", "observatory.cli", "gate", "--scenario", scenario,
            "--dataset", "observatory/data/structured-contracts-v1.jsonl", "--output", str(path),
        ], capture_output=True, text=True)
        assert result.returncode == expected, result.stdout
        reports[scenario] = path
    output = tmp_path / "comparison.json"
    result = subprocess.run([
        sys.executable, "-m", "observatory.cli", "compare",
        "--baseline-report", str(reports["stable"]),
        "--candidate-report", str(reports["regression"]), "--output", str(output),
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(output.read_text())["regressions"] == 7


def test_comparison_cli_requires_reports(tmp_path):
    result = subprocess.run([
        sys.executable, "-m", "observatory.cli", "compare", "--output", str(tmp_path / "out.json"),
    ], capture_output=True, text=True)
    assert result.returncode == 2
