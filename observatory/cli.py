"""Exit status is the quality gate's public contract: 0 passes, 1 blocks, 2 errors."""

import argparse
import json
from pathlib import Path

from .engine import DATASET, run_experiment
from .store import Store
from .telemetry import configure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["gate", "seed"])
    parser.add_argument("--scenario", choices=["stable", "regression"], default="stable")
    parser.add_argument("--provider", choices=["fixture", "compatible"], default="fixture")
    parser.add_argument("--output", type=Path, default=Path("reports/gate.json"))
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--max-quality-drop", type=float, default=0.02)
    parser.add_argument("--max-latency-ratio", type=float, default=1.5)
    args = parser.parse_args()
    if not 0 <= args.max_quality_drop <= 1 or args.max_latency_ratio <= 0:
        parser.error("Quality drop must be in [0,1]; latency ratio must be positive")
    telemetry = configure()
    try:
        result = run_experiment(
            args.provider,
            args.scenario,
            path=args.dataset,
            max_quality_drop=args.max_quality_drop,
            max_latency_ratio=args.max_latency_ratio,
        )
        if args.command == "seed":
            Store().save(result)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result["gate"], indent=2))
        return 0 if args.command == "seed" or result["gate"]["passed"] else 1
    except Exception as exc:
        print(f"Evaluation could not complete: {type(exc).__name__}")
        return 2
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
