from decimal import Decimal

import pytest

from nkap.core.quantity import (
    STORAGE_DECIMALS,
    QuantityPrecisionError,
    parse_quantity,
    quantity_from_storage,
    quantity_to_storage,
)


def test_parse_quantity_respects_unit_decimals() -> None:
    assert parse_quantity("2.5", 3) == Decimal("2.500")
    assert parse_quantity(12, 0) == Decimal("12")
    assert parse_quantity(Decimal("1.250"), 2) == Decimal("1.25")


def test_parse_quantity_refuses_excess_precision() -> None:
    with pytest.raises(QuantityPrecisionError):
        parse_quantity("2.5", 0)  # une pièce ne se coupe pas
    with pytest.raises(QuantityPrecisionError):
        parse_quantity("1.2345", 3)


@pytest.mark.parametrize("bad", [2.5, True])
def test_parse_quantity_refuses_float_and_bool(bad: object) -> None:
    with pytest.raises(TypeError):
        parse_quantity(bad, 3)  # type: ignore[arg-type]


def test_parse_quantity_refuses_bad_input() -> None:
    with pytest.raises(ValueError, match="illisible"):
        parse_quantity("deux", 0)
    with pytest.raises(ValueError, match="non finie"):
        parse_quantity("Infinity", 0)
    with pytest.raises(ValueError, match="décimales"):
        parse_quantity("1", STORAGE_DECIMALS + 1)


def test_storage_round_trip_is_exact() -> None:
    for text in ["0", "1", "-3.5", "0.000001", "1234567.891011", "9000000000000"]:
        value = Decimal(text)
        assert quantity_from_storage(quantity_to_storage(value)) == value


def test_storage_refuses_more_than_six_decimals_and_overflow() -> None:
    with pytest.raises(QuantityPrecisionError):
        quantity_to_storage(Decimal("0.0000001"))
    with pytest.raises(OverflowError):
        quantity_to_storage(Decimal("10000000000000"))
    with pytest.raises(TypeError):
        quantity_to_storage(1.5)  # type: ignore[arg-type]
