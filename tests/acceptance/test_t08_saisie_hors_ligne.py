"""T08 — Couper Internet puis saisir des opérations autorisées.

Résultat attendu (cahier des charges) : saisie locale conservée et marquée en attente.
"""

from datetime import timedelta

from sqlalchemy import func, select

from nkap.site_node.models import OutboxEvent
from support.bench import START, Bench


def test_t08_operations_entered_offline_are_kept_and_marked_pending(bench: Bench) -> None:
    site = bench.add_site("S01")
    site.go_offline()

    # Une semaine sans Internet : on continue à saisir, la synchronisation échoue en silence.
    for day in range(7):
        site.create_notes(3, prefix=f"jour {day}")
        result = site.sync()
        assert result.status == "offline"
        bench.advance(timedelta(days=1))

    notes = site.notes()
    assert len(notes) == 21
    assert {n.sync_status for n in notes} == {"pending"}  # jamais « consolidé » sans accusé
    with site.db.factory() as session:
        statuses = session.execute(
            select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status)
        ).all()
    assert dict(statuses) == {"pending": 42}  # 21 notes + 21 lignes d'audit, rien de perdu

    status = site.status()
    assert status.state == "offline"
    assert status.offline_since == START  # bandeau « hors ligne depuis... »
    assert status.pending_count == 42
    assert status.consecutive_failures == 7
    assert bench.central_note_count() == 0
