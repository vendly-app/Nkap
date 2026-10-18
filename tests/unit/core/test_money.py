from decimal import Decimal

import pytest

from nkap.core.money import AmountPrecisionError, CurrencyMismatchError, Money


def test_money_holds_an_integer_amount_in_minor_units() -> None:
    price = Money(12_500, "XAF")
    assert price.amount == 12_500
    assert price.currency == "XAF"


@pytest.mark.parametrize("bad", [12.5, Decimal("12500"), True, "12500"])
def test_money_refuses_anything_but_int(bad: object) -> None:
    with pytest.raises(TypeError, match="entier"):
        Money(bad, "XAF")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["xaf", "XA", "XAFF", "X1F", "ÉUR"])
def test_money_refuses_invalid_currency_codes(bad: str) -> None:
    with pytest.raises(ValueError, match="devise"):
        Money(1, bad)


def test_arithmetic_and_comparisons_within_one_currency() -> None:
    a, b = Money(1_000, "XAF"), Money(250, "XAF")
    assert a + b == Money(1_250, "XAF")
    assert a - b == Money(750, "XAF")
    assert -a == Money(-1_000, "XAF")
    assert b < a
    assert b <= a
    assert a > b
    assert a >= b
    assert Money.zero("XAF").is_zero
    assert (b - a).is_negative


def test_mixing_currencies_is_refused() -> None:
    xaf, eur = Money(1_000, "XAF"), Money(100, "EUR")
    with pytest.raises(CurrencyMismatchError):
        _ = xaf + eur
    with pytest.raises(CurrencyMismatchError):
        _ = xaf < eur


def test_from_decimal_is_exact_or_refused() -> None:
    assert Money.from_decimal("12500", "XAF", 0) == Money(12_500, "XAF")
    assert Money.from_decimal(Decimal("12.50"), "EUR", 2) == Money(1_250, "EUR")
    with pytest.raises(AmountPrecisionError):
        Money.from_decimal("12500.5", "XAF", 0)
    with pytest.raises(AmountPrecisionError):
        Money.from_decimal("12.505", "EUR", 2)
    with pytest.raises(TypeError):
        Money.from_decimal(12.5, "EUR", 2)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="illisible"):
        Money.from_decimal("douze", "XAF", 0)


def test_to_decimal_for_display() -> None:
    assert Money(1_250, "EUR").to_decimal(2) == Decimal("12.50")
    assert Money(12_500, "XAF").to_decimal(0) == Decimal("12500")
