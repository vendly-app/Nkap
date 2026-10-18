"""T17 — Arrêt brutal pendant une validation ou une synchronisation.

Résultat attendu (analyse critique) : base intègre (``integrity_check``), aucune opération
à moitié appliquée, reprise automatique.

Le processus qui écrit est un vrai processus séparé, tué sans prévenir : c'est ce qui se
passe pour le programme lors d'une coupure de courant ou d'un plantage.
"""

import random
import time

from sqlalchemy import func, select

from nkap.core.db import sqlite_integrity_problems
from nkap.site_node.audit_log import verify_audit_log
from nkap.site_node.models import DemoNote, OutboxEvent, SiteAuditLog
from nkap.site_node.sequences import SYNC_SEQUENCE, current_value
from support import crash
from support.bench import Bench, SimSite

RANDOM_KILLS = 5


def assert_site_consistent(site: SimSite) -> int:
    """Invariants d'une base de site après un arrêt brutal. Renvoie le nombre de notes."""
    assert sqlite_integrity_problems(site.db.engine) == []
    with site.db.factory() as session:
        notes = set(session.scalars(select(DemoNote.id)))
        rows = list(session.scalars(select(OutboxEvent).order_by(OutboxEvent.site_seq)))
        audited = set(session.scalars(select(SiteAuditLog.entity_id)))
        audit_count = session.scalar(select(func.count()).select_from(SiteAuditLog))
        assert verify_audit_log(session).ok
        counter = current_value(session, SYNC_SEQUENCE)
    # Pas de trou, pas de numéro consommé « dans le vide ».
    assert [r.site_seq for r in rows] == list(range(1, len(rows) + 1))
    assert counter == len(rows)
    # Chaque note a exactement son événement et sa ligne d'audit, et rien d'autre.
    created = [r.entity_id for r in rows if r.event_type == "DemoNoteCreated"]
    assert sorted(created) == sorted(notes)
    assert audited == notes
    assert audit_count == len(notes)
    assert len(rows) == 2 * len(notes)
    return len(notes)


def test_t17_death_in_the_middle_of_a_transaction_leaves_nothing_half_done(
    bench: Bench,
) -> None:
    site = bench.add_site("S01")
    site.create_notes(2)
    crash.run_until_exit("die-in-transaction", site.db.url)
    site.db.engine.dispose()  # le site « redémarre »
    assert assert_site_consistent(site) == 2  # la 3e note n'existe pas, sans trace partielle
    site.create_notes(1)  # reprise : le site fonctionne normalement
    assert assert_site_consistent(site) == 3


def test_t17_random_kills_while_writing_never_corrupt_the_site(bench: Bench) -> None:
    site = bench.add_site("S01")
    rng = random.Random(17)
    previous = 0
    for _ in range(RANDOM_KILLS):
        process = crash.start("write-forever", site.db.url)
        crash.wait_ready(process)
        time.sleep(rng.uniform(0.05, 0.3))
        crash.kill(process)
        site.db.engine.dispose()
        count = assert_site_consistent(site)
        assert count > previous  # le processus a bien écrit avant d'être tué
        previous = count
    site.sync()  # reprise automatique : tout part au central
    bench.assert_converged()


def test_t17_death_after_central_commit_but_before_the_ack_is_recovered(bench: Bench) -> None:
    site = bench.add_site("S01")
    site.create_notes(3)
    crash.run_until_exit(
        "die-before-ack", site.db.url, bench.central.url, bench.central.tokens["S01"]
    )
    site.db.engine.dispose()
    assert_site_consistent(site)
    assert bench.central_note_count() == 3  # le central a tout enregistré...
    assert {n.sync_status for n in site.notes()} == {"pending"}  # ... le site ne le sait pas
    assert site.sync().status == "synced"  # reprise : renvoi, dédoublonné par le central
    bench.assert_converged()


def test_t17_random_kills_during_synchronization_are_recovered(bench: Bench) -> None:
    site = bench.add_site("S01")
    rng = random.Random(1717)
    for _ in range(3):
        process = crash.start(
            "sync-forever", site.db.url, bench.central.url, bench.central.tokens["S01"]
        )
        crash.wait_ready(process)
        time.sleep(rng.uniform(0.05, 0.3))
        crash.kill(process)
        site.db.engine.dispose()
        assert_site_consistent(site)
    if bench.central.engine.dialect.name == "sqlite":
        assert sqlite_integrity_problems(bench.central.engine) == []
    assert site.sync().status == "synced"
    bench.assert_converged()
