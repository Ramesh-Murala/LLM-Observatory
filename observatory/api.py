"""Local evaluation API and dashboard served from the same origin."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .engine import DATASET, load_dataset, run_experiment
from .reports import compare_runs, export_csv
from .store import Store
from .telemetry import configure


class ExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["regression", "stable"] = "regression"
    dataset_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    max_quality_drop: float = Field(default=0.02, ge=0, le=1, allow_inf_nan=False)
    max_latency_ratio: float = Field(default=1.5, gt=0, allow_inf_nan=False)


class DatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    jsonl: str = Field(min_length=1, max_length=512_000)


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(database_url)
        telemetry = configure()
        yield
        app.state.store.engine.dispose()
        telemetry.force_flush()

    app = FastAPI(title="LLM Observatory", version="0.1.0", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "local", "remote_enabled": False}

    @app.get("/api/datasets")
    def list_datasets():
        cases, fingerprint = load_dataset()
        builtin = {"id": None, "name": DATASET.stem, "cases": len(cases),
                   "sha256": fingerprint, "builtin": True}
        return [builtin] + [
            {key: value for key, value in dataset.items() if key != "jsonl"}
            for dataset in app.state.store.list_datasets()
        ]

    @app.post("/api/datasets", status_code=201)
    def upload_dataset(request: DatasetRequest):
        try:
            dataset = app.state.store.register_dataset(request.name, request.jsonl)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {key: value for key, value in dataset.items() if key != "jsonl"}

    @app.get("/api/runs")
    def list_runs():
        return [
            {key: value for key, value in run.items() if key != "traces"}
            for run in app.state.store.list()
        ]

    @app.post("/api/runs", status_code=201)
    def create_run(request: ExperimentRequest):
        # The browser can only run free fixtures. Remote runs use the explicit CLI.
        dataset = None
        if request.dataset_id:
            dataset = app.state.store.get_dataset(request.dataset_id)
            if dataset is None:
                raise HTTPException(404, "Dataset not found")
        result = run_experiment(
            scenario=request.scenario,
            dataset_raw=dataset["jsonl"].encode("utf-8") if dataset else None,
            dataset_name=dataset["name"] if dataset else None,
            max_quality_drop=request.max_quality_drop,
            max_latency_ratio=request.max_latency_ratio,
        )
        app.state.store.save(result)
        return result

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        result = app.state.store.get(run_id)
        if result is None:
            raise HTTPException(404, "Experiment not found")
        return result

    @app.get("/api/runs/{run_id}/export")
    def download_run(run_id: str, format: Literal["json", "csv"] = "json"):
        result = get_run(run_id)
        if format == "csv":
            return Response(export_csv(result), media_type="text/csv", headers={
                "Content-Disposition": f'attachment; filename="evaluation-{result["id"]}.csv"'
            })
        return result

    @app.get("/api/compare")
    def compare(baseline: str, candidate: str):
        before, after = get_run(baseline), get_run(candidate)
        try:
            return compare_runs(before, after)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/metrics", response_class=Response)
    def metrics():
        data = app.state.store.list()
        rows = [row for run in data for row in run["traces"]]
        body = (
            "# HELP observatory_retained_runs Number of retained experiments\n"
            "# TYPE observatory_retained_runs gauge\n"
            f"observatory_retained_runs {len(data)}\n"
            "# HELP observatory_retained_failed_cases Failed cases in retained runs\n"
            "# TYPE observatory_retained_failed_cases gauge\n"
            f"observatory_retained_failed_cases {sum(not row['passed'] for row in rows)}\n"
        )
        return Response(body, media_type="text/plain; version=0.0.4")

    app.mount(
        "/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="dashboard"
    )
    return app


app = create_app(os.environ.get("DATABASE_URL"))
