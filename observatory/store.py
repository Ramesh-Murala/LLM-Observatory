"""Portable persistence: SQLite locally, PostgreSQL through DATABASE_URL."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, create_engine, select

from .datasets import parse_dataset

metadata = MetaData()
runs = Table(
    "runs",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
)
datasets = Table(
    "datasets", metadata,
    Column("id", String(64), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("name", String(100), nullable=False),
    Column("payload", JSON, nullable=False),
)


class Store:
    def __init__(self, url: str | None = None):
        url = url or os.environ.get("DATABASE_URL", "sqlite:///observatory.db")
        self.engine = create_engine(
            url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}
        )
        metadata.create_all(self.engine)

    def save(self, payload: dict):
        with self.engine.begin() as connection:
            connection.execute(
                runs.insert().values(
                    id=payload["id"], created_at=datetime.now(timezone.utc), payload=payload
                )
            )

    def list(self) -> list[dict]:
        with self.engine.connect() as connection:
            return list(
                connection.execute(
                    select(runs.c.payload).order_by(runs.c.created_at.desc()).limit(100)
                ).scalars()
            )

    def get(self, run_id: str) -> dict | None:
        with self.engine.connect() as connection:
            return connection.execute(
                select(runs.c.payload).where(runs.c.id == run_id)
            ).scalar_one_or_none()

    def register_dataset(self, name: str, raw: str) -> dict:
        cases, fingerprint = parse_dataset(raw.encode("utf-8"))
        payload = {"id": fingerprint, "name": name, "cases": len(cases),
                   "created_at": datetime.now(timezone.utc).isoformat(), "jsonl": raw}
        with self.engine.begin() as connection:
            # Content-addressed versions are immutable; duplicate uploads are idempotent.
            existing = connection.execute(
                select(datasets.c.payload).where(datasets.c.id == fingerprint)
            ).scalar_one_or_none()
            if existing is not None:
                return existing
            connection.execute(datasets.insert().values(
                id=fingerprint, name=name, created_at=datetime.now(timezone.utc), payload=payload
            ))
        return payload

    def get_dataset(self, dataset_id: str) -> dict | None:
        with self.engine.connect() as connection:
            return connection.execute(
                select(datasets.c.payload).where(datasets.c.id == dataset_id)
            ).scalar_one_or_none()

    def list_datasets(self) -> list[dict]:
        with self.engine.connect() as connection:
            return list(connection.execute(select(datasets.c.payload).order_by(
                datasets.c.created_at.desc()
            ).limit(100)).scalars())
