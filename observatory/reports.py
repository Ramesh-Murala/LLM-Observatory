"""Paired release evidence. Intervals describe cases, not repeated model trials."""

import csv
import io
import math


def wilson(successes: int, total: int) -> list[float]:
    if not total:
        return [0.0, 1.0]
    z = 1.959963984540054
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def compare_runs(baseline: dict, candidate: dict) -> dict:
    """Compare candidate traces from two runs of exactly the same dataset."""
    if baseline["dataset_sha256"] != candidate["dataset_sha256"]:
        raise ValueError("Comparisons require identical dataset fingerprints")
    left = {row["case_id"]: row for row in baseline["traces"] if row["variant"] == "candidate"}
    right = {row["case_id"]: row for row in candidate["traces"] if row["variant"] == "candidate"}
    if not left or left.keys() != right.keys():
        raise ValueError("Comparisons require matching case IDs")
    rows = []
    for case_id, before in left.items():
        after = right[case_id]
        transition = (
            "regressed" if before["passed"] and not after["passed"]
            else "improved" if after["passed"] and not before["passed"]
            else "unchanged_pass" if after["passed"] else "unchanged_fail"
        )
        rows.append({
            "case_id": case_id, "category": after["category"], "transition": transition,
            "baseline_passed": before["passed"], "candidate_passed": after["passed"],
            "baseline_error": before["error"], "candidate_error": after["error"],
        })
    categories = {}
    for category in sorted({row["category"] for row in rows}):
        subset = [row for row in rows if row["category"] == category]
        categories[category] = {
            "cases": len(subset),
            "baseline_pass_rate": sum(row["baseline_passed"] for row in subset) / len(subset),
            "candidate_pass_rate": sum(row["candidate_passed"] for row in subset) / len(subset),
            "regressions": sum(row["transition"] == "regressed" for row in subset),
            "improvements": sum(row["transition"] == "improved" for row in subset),
        }
    count = len(rows)
    before_passed = sum(row["baseline_passed"] for row in rows)
    after_passed = sum(row["candidate_passed"] for row in rows)
    return {
        "baseline_run_id": baseline["id"], "candidate_run_id": candidate["id"],
        "dataset_sha256": baseline["dataset_sha256"], "cases": count,
        "pass_rate_delta": (after_passed - before_passed) / count,
        "baseline_wilson_95": wilson(before_passed, count),
        "candidate_wilson_95": wilson(after_passed, count),
        "regressions": sum(row["transition"] == "regressed" for row in rows),
        "improvements": sum(row["transition"] == "improved" for row in rows),
        "categories": categories, "cases_detail": rows,
        "limitations": (
            "Wilson intervals summarize pass proportions across the supplied cases, assuming "
            "independent representative cases. Synthetic fixtures are not representative. "
            "These are not paired-delta intervals or estimates of live-model repeatability."
        ),
    }


def export_csv(run: dict) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["case_id", "category", "variant", "passed", "latency_ms",
                     "latency_source", "tokens", "usage_source", "estimated_cost_usd", "error"])
    for row in run["traces"]:
        values = [row[key] for key in ["case_id", "category", "variant", "passed", "latency_ms",
                  "latency_source", "tokens", "usage_source", "estimated_cost_usd", "error"]]
        # Treat labels as data when opened in a spreadsheet.
        writer.writerow([
            "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
            else value for value in values
        ])
    return output.getvalue()
