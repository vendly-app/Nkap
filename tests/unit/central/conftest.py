from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import URL

from nkap.core.clock import FakeClock
from support.central import CentralDb, open_central_db
from support.db import sqlite_url
from support.site import SiteDb, open_site_db


@pytest.fixture
def central_db(db_url: URL, clock: FakeClock) -> Iterator[CentralDb]:
    """Base centrale migrée avec les sites S01 et S02 enregistrés (SQLite puis PostgreSQL)."""
    db = open_central_db(db_url, clock)
    yield db
    db.close()


@pytest.fixture
def site_clock() -> FakeClock:
    """Horloge du site S01, indépendante de celle du central."""
    return FakeClock(datetime(2026, 10, 18, 8, 0, tzinfo=UTC))


@pytest.fixture
def site_a(tmp_path: Path, site_clock: FakeClock) -> Iterator[SiteDb]:
    """Base du site S01 (SQLite), qui produit de vrais événements."""
    db = open_site_db(sqlite_url(tmp_path / "site_a.db"), site_clock)
    yield db
    db.close()
