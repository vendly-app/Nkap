"""T09 — Rétablir Internet et synchroniser deux fois.

Résultat attendu (cahier des charges) : données centrales exactes, sans double effet.
"""

from datetime import timedelta

from nkap.central.models import InboxEvent
from nkap.sync.protocol import PROTOCOL_VERSION, PUSH_PATH
from support.bench import Bench
from support.site import site_events


def test_t09_resynchronizing_twice_has_no_double_effect(bench: Bench) -> None:
    site = bench.add_site("S01")
    site.go_offline()
    site.create_notes(5)
    site.sync()
    bench.advance(timedelta(hours=10))

    site.go_online()
    first, second = site.sync(), site.sync()
    assert first.status == "synced"
    assert first.acked == 10
    assert second.status == "synced"
    assert second.sent == 0  # rien à renvoyer : déjà acquitté
    bench.assert_converged()
    assert bench.central_note_count() == 5


def test_t09_a_lost_acknowledgement_does_not_create_duplicates(bench: Bench) -> None:
    site = bench.add_site("S01")
    site.create_notes(5)
    site.link.lose_responses = 1  # le central enregistre tout, mais l'accusé se perd
    assert site.sync().status == "offline"
    assert {n.sync_status for n in site.notes()} == {"pending"}

    assert site.sync().status == "synced"  # renvoi complet du même lot
    assert site.sync().status == "synced"
    bench.assert_converged()
    assert bench.central_note_count() == 5
    assert bench.central.count(InboxEvent) == 10


def test_t09_replaying_an_old_batch_by_hand_changes_nothing(bench: Bench) -> None:
    site = bench.add_site("S01")
    site.create_notes(3)
    site.sync()
    events = [e.model_dump(mode="json") for e in site_events(site.db)]
    body = {"protocol_version": PROTOCOL_VERSION, "site_id": str(site.site_id), "events": events}
    headers = {"Authorization": f"Bearer {bench.central.tokens['S01']}"}
    for _ in range(3):
        response = bench.client.post(PUSH_PATH, json=body, headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["acked_through"] == 6
    bench.assert_converged()
    assert bench.central_note_count() == 3
