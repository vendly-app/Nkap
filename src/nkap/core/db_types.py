"""Types de colonnes au comportement identique sur SQLite et PostgreSQL.

SQLite et PostgreSQL ne gèrent pas les dates et les décimaux de la même façon.
Ces types font en sorte que le reste du code n'ait jamais à s'en soucier :

- ``UTCDateTime`` : date-heure toujours en UTC, toujours avec fuseau à la lecture.
- ``QuantityType`` : quantité ``Decimal`` exacte, stockée en entier de millionièmes.
- ``AmountType`` : montant entier en unités mineures, refuse tout ``float``.

Les identifiants utilisent le type standard ``sqlalchemy.Uuid`` (UUID natif sous
PostgreSQL, texte de 32 caractères sous SQLite).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from nkap.core.clock import require_aware
from nkap.core.quantity import quantity_from_storage, quantity_to_storage


class UTCDateTime(TypeDecorator[datetime]):
    """Date-heure stockée en UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("Une date-heure (datetime) est attendue.")
        utc = require_aware(value).astimezone(UTC)
        if dialect.name == "sqlite":
            # SQLite n'a pas de type date-heure : on stocke un texte UTC sans fuseau,
            # au format fixe, ce qui garde l'ordre chronologique dans les tris.
            return utc.replace(tzinfo=None)
        return utc

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class QuantityType(TypeDecorator[Decimal]):
    """Quantité exacte, stockée en entier de millionièmes (BIGINT)."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> int | None:
        if value is None:
            return None
        return quantity_to_storage(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return quantity_from_storage(int(value))


class AmountType(TypeDecorator[int]):
    """Montant entier en unités mineures (BIGINT). Refuse float et Decimal."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                "Un montant doit être un entier en unités mineures (jamais un float), "
                f"reçu : {type(value).__name__}."
            )
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> int | None:
        if value is None:
            return None
        return int(value)
