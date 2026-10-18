"""Identifiants techniques : UUID version 7 (RFC 9562).

Chaque site génère lui-même ses identifiants, même hors ligne, sans risque de collision :
un UUIDv7 contient 74 bits aléatoires. Ses 48 premiers bits sont l'heure en millisecondes,
ce qui range les nouvelles lignes à la fin des index (bases plus rapides qu'avec des UUID
entièrement aléatoires).

Attention : l'heure contenue dans l'UUID ne sert qu'à l'efficacité des index. Elle n'a
aucune valeur métier et ne sert jamais à ordonner les opérations.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from nkap.core.clock import Clock, SystemClock

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_MS = timedelta(milliseconds=1)
_MAX_TIMESTAMP_MS = (1 << 48) - 1
_SYSTEM_CLOCK = SystemClock()


def uuid7(
    clock: Clock | None = None,
    random_bytes: Callable[[int], bytes] = os.urandom,
) -> uuid.UUID:
    """Génère un UUID version 7."""
    now = (clock or _SYSTEM_CLOCK).now()
    unix_ms = (now - _EPOCH) // _ONE_MS
    if not 0 <= unix_ms <= _MAX_TIMESTAMP_MS:
        raise ValueError("Horloge hors de la plage représentable par un UUIDv7.")
    rand = int.from_bytes(random_bytes(10), "big")  # 80 bits, on en garde 74
    rand_a = (rand >> 62) & 0xFFF  # 12 bits
    rand_b = rand & ((1 << 62) - 1)  # 62 bits
    value = (unix_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


def uuid7_timestamp(value: uuid.UUID) -> datetime:
    """Heure (à la milliseconde) inscrite dans un UUIDv7. Utile pour le diagnostic."""
    if value.version != 7:
        raise ValueError("Ce n'est pas un UUID version 7.")
    return _EPOCH + (value.int >> 80) * _ONE_MS
