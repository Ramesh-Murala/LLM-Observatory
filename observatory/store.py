"""Portable persistence: SQLite locally, PostgreSQL through DATABASE_URL."""

import os
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, create_engine, select

metadata = MetaData()
runs = Table(
    "runs",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
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
