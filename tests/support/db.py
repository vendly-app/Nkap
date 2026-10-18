"""Bases de données jetables pour les tests (SQLite et PostgreSQL)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import URL, create_engine, make_url, text

POSTGRES_ADMIN_URL = os.environ.get("NKAP_TEST_POSTGRES_URL", "")
REQUIRE_POSTGRES = os.environ.get("NKAP_REQUIRE_POSTGRES") == "1"
ENGINES = ("sqlite", "postgresql")


def sqlite_url(path: Path) -> URL:
    return URL.create("sqlite+pysqlite", database=str(path))


@contextmanager
def temporary_postgres_database(admin_url: str = POSTGRES_ADMIN_URL) -> Iterator[URL]:
    """Crée une base PostgreSQL vide et la supprime à la fin du test."""
    admin = create_engine(make_url(admin_url), isolation_level="AUTOCOMMIT")
    name = f"nkap_test_{uuid.uuid4().hex[:16]}"
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        yield make_url(admin_url).set(database=name)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
