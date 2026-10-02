"""Run paired evaluations and decide whether a candidate meets a release policy."""

import hashlib
import json
import math
import os
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .evaluators import evaluate
from .providers import CompatibleProvider, FixtureProvider
from .telemetry import tracer

DATASET = Path(__file__).parent / "data" / "reliability-v1.jsonl"


def load_dataset(path: Path = DATASET) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    cases = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    ids = [case["id"] for case in cases]
    if not cases or len(ids) != len(set(ids)):
        raise ValueError("Dataset must be nonempty with unique case IDs")
    for case in cases:
        evaluate(case, case["baseline"])
    return cases, hashlib.sha256(raw).hexdigest()


def percentile(values: list[float], quantile: float) -> float:
    return sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)]


def gate(
    baseline: dict, candidate: dict, max_quality_drop: float = 0.02, max_latency_ratio: float = 1.5
) -> dict:
    quality_drop = baseline["pass_rate"] - candidate["pass_rate"]
    latency_ratio = candidate["p95_ms"] / max(baseline["p95_ms"], 0.001)
    reasons = []
    if quality_drop > max_quality_drop + 1e-9:
        reasons.append(f"Quality dropped {quality_drop:.1%}; allowed {max_quality_drop:.1%}")
    if latency_ratio > max_latency_ratio:
        reasons.append(f"p95 latency rose {latency_ratio:.2f}×; allowed {max_latency_ratio:.2f}×")
    if candidate["errors"]:
        reasons.append(f"Candidate has {candidate['errors']} provider error(s)")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "quality_drop": quality_drop,
        "latency_ratio": latency_ratio,
        "policy": {"max_quality_drop": max_quality_drop, "max_latency_ratio": max_latency_ratio},
    }


def run_experiment(
    provider_name: str = "fixture",
    scenario: str = "regression",
    path: Path = DATASET,
    max_quality_drop: float = 0.02,
    max_latency_ratio: float = 1.5,
) -> dict:
    if provider_name not in {"fixture", "compatible"}:
        raise ValueError("Unknown provider")
    if scenario not in {"regression", "stable"}:
        raise ValueError("Unknown scenario")
    if provider_name == "compatible" and scenario == "stable":
        raise ValueError("Stable scenario is only available for fixtures")
    provider = FixtureProvider() if provider_name == "fixture" else CompatibleProvider()
    cases, fingerprint = load_dataset(path)
    traces, summaries = [], {}
    prices = {}
    for variant in ("baseline", "candidate"):
        rates = [
            os.environ.get(f"LLM_{variant.upper()}_{kind}_USD_PER_MILLION")
            for kind in ("INPUT", "OUTPUT")
        ]
        prices[variant] = [float(rate) for rate in rates] if all(rates) else None
        if prices[variant] and any(not math.isfinite(rate) or rate < 0 for rate in prices[variant]):
            raise ValueError("Token prices must be finite and nonnegative")
    with tracer.start_as_current_span("experiment") as experiment_span:
        experiment_span.set_attribute("dataset.sha256", fingerprint)
        experiment_span.set_attribute("provider", provider_name)
        for variant in ("baseline", "candidate"):
            rows = []
            for index, case in enumerate(cases):
                with tracer.start_as_current_span("completion") as span:
                    span.set_attribute("case.id", case["id"])
                    span.set_attribute("variant", variant)
                    start = time.perf_counter()
                    error, output, checks, tokens, usage = None, "", [], 0, "unavailable"
                    cost = 0.0 if provider_name == "fixture" else None
                    try:
                        completion = provider.complete(
                            case, "baseline" if scenario == "stable" else variant
                        )
                        output = completion.text
                        tokens = completion.input_tokens + completion.output_tokens
                        usage = completion.usage_source
                        if provider_name != "fixture" and prices[variant] and usage == "provider":
                            cost = (
                                completion.input_tokens * prices[variant][0]
                                + completion.output_tokens * prices[variant][1]
                            ) / 1_000_000
                        checks = [asdict(check) for check in evaluate(case, output)]
                    except Exception as exc:
                        # Do not persist remote response bodies or credential-bearing URLs.
                        error = type(exc).__name__
                    measured_ms = (time.perf_counter() - start) * 1000
                    latency_ms = (
                        (
                            180
                            + (index * 37) % 320
                            + (90 if variant == "candidate" and scenario == "regression" else 0)
                        )
                        if provider_name == "fixture"
                        else measured_ms
                    )
                    context = span.get_span_context()
                    row = {
                        "id": uuid.uuid4().hex,
                        "trace_id": format(context.trace_id, "032x"),
                        "span_id": format(context.span_id, "016x"),
                        "case_id": case["id"],
                        "category": case["category"],
                        "variant": variant,
                        "prompt": case["prompt"],
                        "output": output,
                        "checks": checks,
                        "passed": bool(checks)
                        and all(check["passed"] for check in checks)
                        and error is None,
                        "latency_ms": round(latency_ms, 2),
                        "latency_source": "simulated" if provider_name == "fixture" else "measured",
                        "tokens": tokens,
                        "usage_source": usage,
                        "estimated_cost_usd": cost,
                        "error": error,
                    }
                    span.set_attribute("evaluation.passed", row["passed"])
                    rows.append(row)
            summaries[variant] = {
                "cases": len(rows),
                "pass_rate": sum(row["passed"] for row in rows) / len(rows),
                "p95_ms": percentile([row["latency_ms"] for row in rows], 0.95),
                "tokens": sum(row["tokens"] for row in rows),
                "errors": sum(row["error"] is not None for row in rows),
                "estimated_cost_usd": sum(row["estimated_cost_usd"] for row in rows)
                if all(row["estimated_cost_usd"] is not None for row in rows)
                else None,
            }
            traces.extend(rows)
    return {
        "id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": path.stem,
        "dataset_sha256": fingerprint,
        "provider": provider_name,
        "scenario": scenario,
        "models": {
            variant: os.environ.get(f"LLM_{variant.upper()}_MODEL", "unspecified")
            if provider_name != "fixture"
            else f"fixture-{variant}"
            for variant in ("baseline", "candidate")
        },
        "pricing_usd_per_million": prices if provider_name != "fixture" else None,
        "summaries": summaries,
        "gate": gate(
            summaries["baseline"], summaries["candidate"], max_quality_drop, max_latency_ratio
        ),
        "traces": traces,
    }
