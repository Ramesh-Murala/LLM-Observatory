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
