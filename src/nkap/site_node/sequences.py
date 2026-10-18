"""Compteurs locaux du site (table ``site_sequences``).

Un compteur est incrémenté **dans la transaction de l'opération** qui consomme le numéro :
si l'opération échoue, le numéro n'est pas consommé. Il n'y a donc jamais de trou.

Le compteur ``sync`` fournit le ``site_seq`` des événements de synchronisation.
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nkap.site_node.models import SiteSequence

SYNC_SEQUENCE = "sync"


def allocate(session: Session, name: str, count: int = 1) -> range:
    """Réserve ``count`` valeurs consécutives du compteur ``name`` et renvoie la plage."""
    if count < 1:
        raise ValueError("Il faut réserver au moins une valeur.")
    stmt = (
        update(SiteSequence)
        .where(SiteSequence.name == name)
        .values(last_value=SiteSequence.last_value + count)
        .returning(SiteSequence.last_value)
    )
    options = {"synchronize_session": False}
    last = session.execute(stmt, execution_options=options).scalar_one_or_none()
    if last is None:
        # Premier usage de ce compteur : on le crée. Le « savepoint » protège contre le
        # cas (PostgreSQL) où une autre transaction le crée au même instant.
        try:
            with session.begin_nested():
                session.add(SiteSequence(name=name, last_value=count))
            last = count
        except IntegrityError:
            last = session.execute(stmt, execution_options=options).scalar_one()
    return range(last - count + 1, last + 1)


def current_value(session: Session, name: str) -> int:
    """Dernière valeur attribuée (0 si le compteur n'a jamais servi)."""
    row = session.get(SiteSequence, name)
    return 0 if row is None else row.last_value
