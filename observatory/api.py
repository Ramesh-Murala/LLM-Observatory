"""Local evaluation API and dashboard served from the same origin."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import run_experiment
from .store import Store
from .telemetry import configure


class ExperimentRequest(BaseModel):
    scenario: Literal["regression", "stable"] = "regression"


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

    @app.get("/api/runs")
    def list_runs():
        return [
            {key: value for key, value in run.items() if key != "traces"}
            for run in app.state.store.list()
        ]

    @app.post("/api/runs", status_code=201)
    def create_run(request: ExperimentRequest):
        # The browser can only run free fixtures. Remote runs use the explicit CLI.
        result = run_experiment(scenario=request.scenario)
        app.state.store.save(result)
        return result

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        result = app.state.store.get(run_id)
        if result is None:
            raise HTTPException(404, "Experiment not found")
        return result

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
