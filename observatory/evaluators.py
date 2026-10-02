"""Small, deterministic checks. These are contracts, not a general safety classifier."""

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    reason: str


def evaluate(case: dict, output: str) -> list[Check]:
    checks = []
    for rule in case["checks"]:
        kind = rule["type"]
        if kind == "exact":
            passed = output.strip().casefold() == rule["value"].strip().casefold()
            reason = "Response matches reference" if passed else "Response differs from reference"
        elif kind == "contains":
            passed = rule["value"].casefold() in output.casefold()
            reason = "Required phrase found" if passed else "Required phrase missing"
        elif kind == "excludes":
            passed = rule["value"].casefold() not in output.casefold()
            reason = "Restricted phrase absent" if passed else "Restricted phrase found"
        elif kind == "max_words":
            count = len(re.findall(r"\S+", output))
            passed = count <= rule["value"]
            reason = f"{count} words; limit {rule['value']}"
        elif kind == "json":
            try:
                value = json.loads(output)
                passed = isinstance(value, dict) and all(
                    key in value and type(value[key]).__name__ == expected
                    for key, expected in rule["fields"].items()
                )
                reason = "JSON contract satisfied" if passed else "JSON field contract violated"
            except (json.JSONDecodeError, TypeError):
                passed, reason = False, "Response is not valid JSON"
        else:
            raise ValueError(f"Unsupported evaluator: {kind}")
        checks.append(Check(kind, passed, reason))
    if not checks:
        raise ValueError("Each case must define at least one check")
    return checks
