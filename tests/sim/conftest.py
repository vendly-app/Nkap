from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import URL

from support.bench import Bench


@pytest.fixture
def bench(tmp_path: Path, db_url: URL) -> Iterator[Bench]:
    """Banc vide : central sur SQLite puis sur PostgreSQL, sites ajoutés par le test."""
    with Bench(tmp_path, central_url=db_url) as b:
        yield b
