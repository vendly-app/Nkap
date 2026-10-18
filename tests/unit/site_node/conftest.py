from collections.abc import Iterator

import pytest
from sqlalchemy import URL

from nkap.core.clock import FakeClock
from support.site import SiteDb, open_site_db


@pytest.fixture
def site_db(db_url: URL, clock: FakeClock) -> Iterator[SiteDb]:
    """Base de site migrée et initialisée (site S01), sur SQLite puis PostgreSQL."""
    db = open_site_db(db_url, clock)
    yield db
    db.close()
