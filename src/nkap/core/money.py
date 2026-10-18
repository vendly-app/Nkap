"""Montants d'argent.

Règle du projet : un montant est un **entier** exprimé dans la plus petite unité de la
devise (le franc CFA n'a pas de centimes : 12 500 FCFA s'écrit ``12500``). Les nombres
à virgule flottante (``float``) sont interdits : ils produisent des erreurs d'arrondi
(0,1 + 0,2 ne fait pas exactement 0,3 en ``float``).

Le nombre de décimales d'une devise vient du référentiel des devises (table
``currencies``, étape 2). Il est donc passé en paramètre, jamais deviné ici.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class CurrencyMismatchError(ValueError):
    """Opération entre deux devises différentes."""


class AmountPrecisionError(ValueError):
    """Montant avec plus de décimales que la devise n'en autorise."""


def _check_currency(code: str) -> str:
    if not (len(code) == 3 and code.isascii() and code.isalpha() and code.isupper()):
        raise ValueError(f"Code devise invalide : {code!r} (3 lettres majuscules, ex. XAF).")
    return code


def _check_amount(amount: object) -> int:
    # bool est un sous-type de int en Python : on le refuse explicitement.
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise TypeError(
            "Un montant doit être un entier en unités mineures (jamais un float), "
            f"reçu : {type(amount).__name__}."
        )
    return amount


@dataclass(frozen=True, slots=True)
class Money:
    """Montant exact dans une devise donnée."""

    amount: int
    currency: str

    def __post_init__(self) -> None:
        _check_amount(self.amount)
        _check_currency(self.currency)

    # --- Conversions ---------------------------------------------------------------

    @classmethod
    def from_decimal(cls, value: Decimal | str | int, currency: str, decimals: int) -> Money:
        """Convertit un montant « humain » (ex. ``"12.50"`` en euros) en unités mineures.

        Refuse toute perte de précision : ``"12.505"`` avec 2 décimales est une erreur,
        jamais un arrondi silencieux.
        """
        if isinstance(value, float | bool):
            raise TypeError("Les float sont interdits pour les montants.")
        try:
            dec = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Montant illisible : {value!r}.") from exc
        if not dec.is_finite():
            raise ValueError("Montant non fini refusé.")
        scaled = dec.scaleb(decimals)
        if scaled != scaled.to_integral_value():
            raise AmountPrecisionError(
                f"{value} a plus de {decimals} décimale(s) autorisée(s) pour {currency}."
            )
        return cls(int(scaled), currency)

    def to_decimal(self, decimals: int) -> Decimal:
        """Montant « humain » (ex. ``Decimal("12.50")``) pour l'affichage."""
        return Decimal(self.amount).scaleb(-decimals)

    # --- Arithmétique (même devise uniquement) -------------------------------------

    def _same_currency(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError("Opération possible uniquement entre deux Money.")
        if other.currency != self.currency:
            raise CurrencyMismatchError(
                f"Devises différentes : {self.currency} et {other.currency}."
            )

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount >= other.amount

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(0, currency)
