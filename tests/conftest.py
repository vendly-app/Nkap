"""Configuration commune des tests.

La fixture ``db_url`` fait tourner un même test sur SQLite puis sur PostgreSQL.
PostgreSQL n'est utilisé que si ``NKAP_TEST_POSTGRES_URL`` est défini (sinon ces
variantes sont sautées, sauf en CI où ``NKAP_REQUIRE_POSTGRES=1`` les rend obligatoires).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import URL

from nkap.core.clock import FakeClock
from support.bench import Bench
from support.db import (
    ENGINES,
    POSTGRES_ADMIN_URL,
    REQUIRE_POSTGRES,
    sqlite_url,
    temporary_postgres_database,
)


def pytest_configure(config: pytest.Config) -> None:
    if REQUIRE_POSTGRES and not POSTGRES_ADMIN_URL:
        raise pytest.UsageError(
            "NKAP_REQUIRE_POSTGRES=1 mais NKAP_TEST_POSTGRES_URL n'est pas défini."
        )


def make_db_url(engine_name: str, tmp_path: Path, name: str = "test") -> Iterator[URL]:
    if engine_name == "sqlite":
        yield sqlite_url(tmp_path / f"{name}.db")
        return
    if not POSTGRES_ADMIN_URL:
        pytest.skip("PostgreSQL non configuré (NKAP_TEST_POSTGRES_URL).")
    with temporary_postgres_database() as url:
        yield url


@pytest.fixture(params=ENGINES)
def db_url(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[URL]:
    """URL d'une base vide, sur SQLite puis sur PostgreSQL."""
    yield from make_db_url(request.param, tmp_path)


@pytest.fixture
def sqlite_db_url(tmp_path: Path) -> URL:
    """URL d'une base SQLite vide (tests propres à SQLite)."""
    return sqlite_url(tmp_path / "test.db")


@pytest.fixture
def clock() -> FakeClock:
    """Horloge pilotée, fixée au 18 octobre 2026 à 08:00 UTC."""
    return FakeClock(datetime(2026, 10, 18, 8, 0, tzinfo=UTC))


@pytest.fixture
def bench(tmp_path: Path, db_url: URL) -> Iterator[Bench]:
    """Banc de simulation vide : central sur SQLite puis sur PostgreSQL."""
    with Bench(tmp_path, central_url=db_url) as b:
        yield b
