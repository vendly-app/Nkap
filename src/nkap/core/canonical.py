"""Écriture « canonique » en JSON et empreintes SHA-256.

Pour calculer une empreinte (hachage) fiable, la même donnée doit toujours produire
exactement le même texte : clés triées, pas d'espaces, dates en UTC au format fixe,
nombres décimaux sous forme de texte. C'est ce que fait :func:`canonical_json`.

Elle sert au journal d'audit chaîné et à la vérification des événements reçus.
Les ``float`` y sont refusés, comme partout ailleurs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from nkap.core.clock import require_aware

JsonValue = Any


def format_datetime(value: datetime) -> str:
    """Date-heure en UTC, toujours au même format : ``2026-10-18T21:36:00.000000Z``."""
    utc = require_aware(value).astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def format_decimal(value: Decimal) -> str:
    """Décimal sous sa forme la plus courte : ``Decimal("1.500")`` devient ``"1.5"``."""
    if not value.is_finite():
        raise ValueError("Décimal non fini refusé.")
    if value.is_zero():
        return "0"
    return format(value.normalize(), "f")


def to_jsonable(value: object) -> JsonValue:
    """Convertit une valeur Python en structure JSON simple, de façon déterministe."""
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise TypeError("Les float sont interdits (montants et quantités exacts uniquement).")
    if isinstance(value, Decimal):
        return format_decimal(value)
    if isinstance(value, datetime):  # avant date : datetime est un sous-type de date
        return format_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Les clés JSON doivent être des textes.")
            result[key] = to_jsonable(item)
        return result
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    raise TypeError(f"Type non sérialisable en JSON canonique : {type(value).__name__}.")


def canonical_json(value: object) -> str:
    """Texte JSON canonique (déterministe) d'une valeur."""
    return json.dumps(
        to_jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_hex(text: str) -> str:
    """Empreinte SHA-256 d'un texte (encodé en UTF-8), en hexadécimal."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
