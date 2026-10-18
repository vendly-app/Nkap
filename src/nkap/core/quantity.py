"""Quantités (articles, kilos, litres...).

Une quantité est un ``Decimal`` (nombre décimal exact), jamais un ``float``. Chaque unité
définit son nombre de décimales autorisées (``units.decimals``) : 0 pour des pièces,
3 pour des kilos au gramme près, etc.

En base, toutes les quantités sont stockées en **millionièmes** (entier), ce qui donne le
même comportement exact sur SQLite et PostgreSQL, y compris pour les sommes calculées
par la base. Une unité ne peut donc pas avoir plus de 6 décimales.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

STORAGE_DECIMALS = 6
"""Nombre de décimales conservées en base pour toute quantité."""

_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


class QuantityPrecisionError(ValueError):
    """Quantité avec plus de décimales que l'unité n'en autorise."""


def parse_quantity(value: Decimal | str | int, decimals: int) -> Decimal:
    """Valide une quantité saisie pour une unité ayant ``decimals`` décimales.

    Renvoie la quantité ramenée au format de l'unité (``"2.5"`` en kilos à 3 décimales
    devient ``Decimal("2.500")``). Refuse les float et toute perte de précision.
    """
    if not 0 <= decimals <= STORAGE_DECIMALS:
        raise ValueError(f"Une unité accepte de 0 à {STORAGE_DECIMALS} décimales.")
    if isinstance(value, float | bool):
        raise TypeError("Les float sont interdits pour les quantités.")
    try:
        dec = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Quantité illisible : {value!r}.") from exc
    if not dec.is_finite():
        raise ValueError("Quantité non finie refusée.")
    quantum = Decimal(1).scaleb(-decimals)
    rounded = dec.quantize(quantum)
    if rounded != dec:
        raise QuantityPrecisionError(
            f"La quantité {value} a plus de {decimals} décimale(s) autorisée(s)."
        )
    return rounded


def quantity_to_storage(value: Decimal) -> int:
    """Convertit une quantité en entier de millionièmes (format de stockage)."""
    if isinstance(value, bool) or not isinstance(value, Decimal | int):
        raise TypeError(
            "Une quantité doit être un Decimal ou un entier (jamais un float), "
            f"reçu : {type(value).__name__}."
        )
    dec = Decimal(value)
    if not dec.is_finite():
        raise ValueError("Quantité non finie refusée.")
    scaled = dec.scaleb(STORAGE_DECIMALS)
    if scaled != scaled.to_integral_value():
        raise QuantityPrecisionError(
            f"La quantité {value} dépasse la précision de stockage ({STORAGE_DECIMALS} décimales)."
        )
    stored = int(scaled)
    if not _INT64_MIN <= stored <= _INT64_MAX:
        raise OverflowError("Quantité trop grande pour être stockée.")
    return stored


def quantity_from_storage(stored: int) -> Decimal:
    """Inverse de :func:`quantity_to_storage`."""
    return Decimal(stored).scaleb(-STORAGE_DECIMALS)
