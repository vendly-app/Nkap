"""Horloge injectable.

Le code ne lit jamais l'heure directement (``datetime.now()``) : il passe par un objet
``Clock``. En production, c'est l'horloge du système (``SystemClock``). Dans les tests,
c'est une horloge pilotée (``FakeClock``) qu'on peut avancer, reculer ou décaler par site.
C'est indispensable pour tester les coupures longues et les PC dont l'heure est fausse.

Rappel (décision 008) : l'heure d'un PC ne sert JAMAIS à ordonner les événements.
L'ordre est donné par le compteur ``site_seq``.
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    """Source de l'heure courante."""

    def now(self) -> datetime:
        """Heure courante, toujours avec le fuseau UTC."""
        ...


def require_aware(value: datetime) -> datetime:
    """Refuse une date-heure sans fuseau horaire (source classique de décalages)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Date-heure sans fuseau horaire refusée : préciser le fuseau (UTC).")
    return value


class SystemClock:
    """Horloge réelle du système."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Horloge pilotée par les tests (sûre en cas d'accès depuis plusieurs fils)."""

    def __init__(self, start: datetime) -> None:
        self._now = require_aware(start).astimezone(UTC)
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return self._now

    def advance(self, delta: timedelta) -> None:
        """Avance (ou recule si ``delta`` est négatif) l'horloge."""
        with self._lock:
            self._now = self._now + delta

    def set(self, value: datetime) -> None:
        """Place l'horloge à une date-heure précise."""
        with self._lock:
            self._now = require_aware(value).astimezone(UTC)


def local_date(clock: Clock, timezone: str) -> date:
    """Date du jour dans le fuseau du site (ex. ``Africa/Douala``).

    Sert de valeur par défaut à la date métier d'une opération saisie aujourd'hui.
    """
    return clock.now().astimezone(ZoneInfo(timezone)).date()
