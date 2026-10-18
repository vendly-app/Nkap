import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nkap.core.canonical import canonical_json, format_decimal, sha256_hex


def test_canonical_json_is_sorted_and_compact() -> None:
    assert canonical_json({"b": 1, "a": [True, None, "é"]}) == '{"a":[true,null,"é"],"b":1}'


def test_same_data_in_any_order_gives_same_hash() -> None:
    one = {"x": 1, "y": {"b": 2, "a": 3}}
    two = {"y": {"a": 3, "b": 2}, "x": 1}
    assert sha256_hex(canonical_json(one)) == sha256_hex(canonical_json(two))


def test_datetimes_are_written_in_utc_with_a_fixed_format() -> None:
    douala = timezone(timedelta(hours=1))
    value = datetime(2026, 10, 18, 9, 0, tzinfo=douala)
    assert canonical_json(value) == '"2026-10-18T08:00:00.000000Z"'
    assert canonical_json(datetime(2026, 10, 18, 8, 0, tzinfo=UTC)) == canonical_json(value)


def test_naive_datetimes_are_refused() -> None:
    with pytest.raises(ValueError, match="sans fuseau"):
        canonical_json(datetime(2026, 10, 18))  # noqa: DTZ001


def test_decimals_dates_and_uuids_are_written_as_text() -> None:
    ident = uuid.UUID("01890000-0000-7000-8000-000000000000")
    data = {"q": Decimal("1.500"), "d": date(2026, 10, 18), "id": ident}
    assert canonical_json(data) == (
        '{"d":"2026-10-18","id":"01890000-0000-7000-8000-000000000000","q":"1.5"}'
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1.500", "1.5"), ("100", "100"), ("0.000", "0"), ("-0", "0"), ("1E+3", "1000")],
)
def test_format_decimal_is_canonical(value: str, expected: str) -> None:
    assert format_decimal(Decimal(value)) == expected


def test_floats_are_refused_everywhere() -> None:
    with pytest.raises(TypeError, match="float"):
        canonical_json({"montant": 0.1})
    with pytest.raises(TypeError, match="float"):
        canonical_json([1, 2.0])


def test_unknown_types_and_non_text_keys_are_refused() -> None:
    with pytest.raises(TypeError):
        canonical_json({1: "a"})
    with pytest.raises(TypeError):
        canonical_json(object())
