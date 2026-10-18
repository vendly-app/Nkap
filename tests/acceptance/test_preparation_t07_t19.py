"""Préparation de T07 (deux sites hors ligne en même temps) et T19 (horloges décalées).

Les tests complets T07 et T19 viendront avec les transferts (étape 4) et le blocage de la
saisie (étape 7) ; ici on vérifie déjà le socle : identifiants et ordre.
"""

from datetime import timedelta

from sqlalchemy import select

from nkap.central.models import CentralDemoNote, InboxEvent
from support.bench import Bench


def test_two_sites_working_offline_at_the_same_time_never_collide(bench: Bench) -> None:
    s1, s2 = bench.add_site("S01"), bench.add_site("S02")
    s1.go_offline()
    s2.go_offline()
    for _ in range(5):  # saisies entremêlées sur les deux sites, sans Internet
        s1.create_notes(2)
        s2.create_notes(2)
    bench.sync_all()
    bench.advance(timedelta(days=2))
    s1.go_online()
    s2.go_online()
    bench.sync_all()
    bench.assert_converged()
    with bench.central.factory() as session:
        ids = list(session.scalars(select(CentralDemoNote.id)))
        events = list(session.scalars(select(InboxEvent.event_id)))
    assert len(ids) == len(set(ids)) == 20  # aucun doublon d'identifiant
    assert len(events) == len(set(events)) == 40


def test_wrong_pc_clocks_do_not_change_the_order_and_raise_an_alert(bench: Bench) -> None:
    early, late = bench.add_site("S01"), bench.add_site("S02")
    early.clock.advance(timedelta(days=-2))  # PC en retard de 2 jours
    late.clock.advance(timedelta(days=2))  # PC en avance de 2 jours
    for site in (early, late):
        site.create_notes(2)
        site.clock.advance(timedelta(minutes=-30))  # l'heure recule entre deux saisies
        site.create_notes(2)
    bench.sync_all()
    bench.assert_converged()  # ordre au central = ordre site_seq, malgré les heures fausses
    with bench.central.factory() as session:
        for site in (early, late):
            seqs = list(
                session.scalars(
                    select(InboxEvent.site_seq)
                    .where(InboxEvent.site_id == site.site_id)
                    .order_by(InboxEvent.received_at, InboxEvent.site_seq)
                )
            )
            assert seqs == list(range(1, 9))
    assert early.status().clock_alert
    assert late.status().clock_alert
    assert early.status().clock_offset_seconds is not None
    assert late.status().clock_offset_seconds is not None
