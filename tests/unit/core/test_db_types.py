"""Les types de colonnes se comportent à l'identique sur SQLite et PostgreSQL."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import (
    URL,
    Column,
    Date,
    Engine,
    Integer,
    MetaData,
    Table,
    Uuid,
    func,
    insert,
    select,
)
from sqlalchemy.exc import StatementError

from nkap.core.db import create_db_engine
from nkap.core.db_types import AmountType, QuantityType, UTCDateTime

metadata = MetaData()
samples = Table(
    "samples",
    metadata,
    Column("pk", Integer, primary_key=True),
    Column("ident", Uuid),
    Column("at", UTCDateTime),
    Column("qty", QuantityType),
    Column("amount", AmountType),
    Column("day", Date),
)


@pytest.fixture
def engine(db_url: URL) -> Iterator[Engine]:
    eng = create_db_engine(db_url)
    metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_values_round_trip_identically(engine: Engine) -> None:
    ident = uuid.uuid4()
    douala = timezone(timedelta(hours=1))
    at = datetime(2026, 10, 18, 9, 30, 15, 123456, tzinfo=douala)
    with engine.begin() as conn:
        conn.execute(
            insert(samples).values(
                pk=1,
                ident=ident,
                at=at,
                qty=Decimal("2.125"),
                amount=12_500,
                day=date(2026, 10, 18),
            )
        )
    with engine.connect() as conn:
        row = conn.execute(select(samples)).one()
    assert row.ident == ident
    assert row.at == at
    assert row.at.utcoffset() == timedelta(0)  # toujours relu en UTC
    assert row.qty == Decimal("2.125")
    assert isinstance(row.qty, Decimal)
    assert row.amount == 12_500
    assert isinstance(row.amount, int)
    assert row.day == date(2026, 10, 18)


def test_database_sums_of_quantities_are_exact(engine: Engine) -> None:
    with engine.begin() as conn:
        for pk, qty in enumerate(["0.1", "0.2", "0.000001"], start=1):
            conn.execute(insert(samples).values(pk=pk, qty=Decimal(qty)))
    with engine.connect() as conn:
        total = conn.execute(select(func.sum(samples.c.qty))).scalar_one()
    assert total == Decimal("0.300001")  # 0.1 + 0.2 en float donnerait 0.30000000000000004


def test_datetimes_sort_chronologically(engine: Engine) -> None:
    base = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)
    offsets = [timedelta(hours=5), timedelta(microseconds=1), timedelta(days=-400)]
    with engine.begin() as conn:
        for pk, delta in enumerate(offsets, start=1):
            conn.execute(insert(samples).values(pk=pk, at=base + delta))
        after = conn.execute(select(samples.c.pk).where(samples.c.at > base)).scalars().all()
    with engine.connect() as conn:
        order = conn.execute(select(samples.c.pk).order_by(samples.c.at)).scalars().all()
    assert order == [3, 2, 1]
    assert sorted(after) == [1, 2]


@pytest.mark.parametrize(
    ("column", "bad"),
    [
        ("at", datetime(2026, 10, 18, 8, 0)),  # noqa: DTZ001 - date sans fuseau
        ("qty", 1.5),
        ("qty", Decimal("0.0000001")),
        ("amount", 12.5),
        ("amount", Decimal("12500")),
    ],
)
def test_unsafe_values_are_refused(engine: Engine, column: str, bad: object) -> None:
    with pytest.raises(StatementError), engine.begin() as conn:
        conn.execute(insert(samples).values(pk=1, **{column: bad}))
