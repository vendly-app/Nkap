"""Réception des lots au central : une seule fois, dans l'ordre, tout ou rien."""

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from nkap.central.handlers import CENTRAL_HANDLERS
from nkap.central.ingest import InvalidBatchError, SiteMismatchError
from nkap.central.models import CentralDemoNote, InboxEvent, SiteAuditEntry, SyncSiteState
from nkap.core.clock import FakeClock
from nkap.core.orm import Actor
from nkap.events.catalog import build_registry
from nkap.events.envelope import EventEnvelope
from nkap.site_node.demo_notes import create_demo_note
from nkap.sync.protocol import PushStatus
from support.central import CentralDb
from support.events import SITE_A, SITE_B, make_envelope
from support.site import SiteDb, site_events


def _notes(site: SiteDb, count: int) -> list[EventEnvelope]:
    for i in range(count):
        create_demo_note(site.uow, f"note {i}", actor=Actor.system())
    return site_events(site)


def _note_event(seq: int, **overrides: Any) -> EventEnvelope:
    """Événement DemoNoteCreated isolé (transaction d'un seul événement)."""
    return make_envelope(site_seq=seq, **overrides)


def _state(db: CentralDb) -> SyncSiteState:
    with db.factory() as session:
        state = session.get(SyncSiteState, SITE_A)
        assert state is not None
        return state


def test_events_from_a_site_are_applied_once_and_acknowledged(
    central_db: CentralDb, site_a: SiteDb
) -> None:
    events = _notes(site_a, 3)  # 3 notes = 6 événements (note + audit)
    response = central_db.push("S01", events)
    assert response.status is PushStatus.OK
    assert response.acked_through == 6
    assert response.expected_next == 7
    assert response.rejected is None
    assert central_db.count(InboxEvent) == 6
    assert central_db.count(CentralDemoNote) == 3
    assert central_db.count(SiteAuditEntry) == 3
    state = _state(central_db)
    assert (state.last_seq, state.audit_last_seq) == (6, 3)


def test_sending_the_same_batch_twice_has_a_single_effect(
    central_db: CentralDb, site_a: SiteDb
) -> None:
    events = _notes(site_a, 3)
    central_db.push("S01", events)
    again = central_db.push("S01", events)
    assert again.status is PushStatus.OK
    assert again.acked_through == 6
    assert central_db.count(InboxEvent) == 6
    assert central_db.count(CentralDemoNote) == 3


def test_overlapping_batches_are_merged_without_duplicates(
    central_db: CentralDb, site_a: SiteDb
) -> None:
    events = _notes(site_a, 3)
    assert central_db.push("S01", events[:2]).acked_through == 2
    response = central_db.push("S01", events)
    assert response.status is PushStatus.OK
    assert response.acked_through == 6
    assert central_db.count(CentralDemoNote) == 3


def test_a_batch_after_a_gap_is_held_back(central_db: CentralDb, site_a: SiteDb) -> None:
    events = _notes(site_a, 3)
    response = central_db.push("S01", events[2:])  # commence au n°3 : 1 et 2 manquent
    assert response.status is PushStatus.GAP
    assert response.acked_through == 0
    assert response.expected_next == 1
    assert central_db.count(InboxEvent) == 0
    assert central_db.push("S01", events).acked_through == 6


def test_progress_before_a_gap_is_kept(central_db: CentralDb, site_a: SiteDb) -> None:
    events = _notes(site_a, 3)
    response = central_db.push("S01", events[:2] + events[4:])
    assert response.status is PushStatus.GAP
    assert response.acked_through == 2
    assert response.expected_next == 3
    assert central_db.count(CentralDemoNote) == 1


def test_a_reused_sequence_number_is_a_conflict(central_db: CentralDb) -> None:
    central_db.push("S01", [_note_event(1), _note_event(2)])
    response = central_db.push("S01", [_note_event(2)])  # autre événement, même numéro
    assert response.status is PushStatus.CONFLICT
    assert response.rejected is not None
    assert response.rejected.code == "sync.seq_conflict"
    assert "sauvegarde" in response.rejected.message
    assert response.acked_through == 2


def test_same_event_id_with_different_content_is_a_conflict(central_db: CentralDb) -> None:
    original = _note_event(1, payload={"text": "original"})
    central_db.push("S01", [original])
    forged = _note_event(1, event_id=original.event_id, tx_id=original.tx_id, payload={"text": "x"})
    response = central_db.push("S01", [forged])
    assert response.status is PushStatus.CONFLICT
    assert response.rejected is not None
    assert response.rejected.code == "sync.event_mismatch"
    with central_db.factory() as session:
        texts = list(session.scalars(select(CentralDemoNote.text)))
    assert texts == ["original"]


def test_an_unknown_event_type_blocks_the_stream_at_that_point(central_db: CentralDb) -> None:
    response = central_db.push(
        "S01", [_note_event(1), _note_event(2, event_type="StockShipped"), _note_event(3)]
    )
    assert response.status is PushStatus.REJECTED
    assert response.acked_through == 1
    assert response.rejected is not None
    assert response.rejected.site_seq == 2
    assert response.rejected.code == "event.unknown_type"
    assert central_db.count(InboxEvent) == 1


def test_an_invalid_payload_is_rejected(central_db: CentralDb) -> None:
    response = central_db.push("S01", [_note_event(1, payload={"text": ""})])
    assert response.status is PushStatus.REJECTED
    assert response.rejected is not None
    assert response.rejected.code == "event.invalid_payload"
    assert central_db.count(InboxEvent) == 0


def test_an_incomplete_transaction_is_rejected(central_db: CentralDb, site_a: SiteDb) -> None:
    events = _notes(site_a, 1)  # une transaction de 2 événements
    response = central_db.push("S01", events[:1])
    assert response.status is PushStatus.REJECTED
    assert response.rejected is not None
    assert response.rejected.code == "sync.incomplete_tx"
    assert central_db.count(InboxEvent) == 0


def test_a_transaction_is_applied_all_or_nothing(central_db: CentralDb, site_a: SiteDb) -> None:
    note, audit = _notes(site_a, 1)
    broken_audit = audit.model_copy(update={"payload": {**audit.payload, "hash": "a" * 64}})
    response = central_db.push("S01", [note, broken_audit])
    assert response.status is PushStatus.REJECTED
    assert response.rejected is not None
    assert response.rejected.code == "audit.chain_broken"
    assert response.rejected.site_seq == 2
    assert response.acked_through == 0
    # La note (1er événement, valide) n'a pas été conservée : tout ou rien.
    assert central_db.count(CentralDemoNote) == 0
    assert central_db.count(InboxEvent) == 0


def test_central_checks_the_audit_chain_across_batches(
    central_db: CentralDb, site_a: SiteDb
) -> None:
    events = _notes(site_a, 2)
    central_db.push("S01", events[:2])
    assert central_db.push("S01", events[2:]).status is PushStatus.OK
    with central_db.factory() as session:
        entries = list(session.scalars(select(SiteAuditEntry).order_by(SiteAuditEntry.chain_seq)))
    assert [e.chain_seq for e in entries] == [1, 2]
    assert entries[1].prev_hash == entries[0].hash


def test_a_rewritten_site_audit_log_is_detected(central_db: CentralDb, site_a: SiteDb) -> None:
    events = _notes(site_a, 2)
    central_db.push("S01", events[:2])
    note, audit = events[2:]
    # Ligne d'audit « réécrite » : chaînée sur une empreinte que le central ne connaît pas.
    forged = audit.model_copy(update={"payload": {**audit.payload, "prev_hash": "b" * 64}})
    response = central_db.push("S01", [note, forged])
    assert response.status is PushStatus.REJECTED
    assert response.rejected is not None
    assert response.rejected.code == "audit.chain_broken"


def test_an_object_created_twice_is_rejected(central_db: CentralDb) -> None:
    entity = uuid.uuid4()
    response = central_db.push(
        "S01", [_note_event(1, entity_id=entity), _note_event(2, entity_id=entity)]
    )
    assert response.status is PushStatus.REJECTED
    assert response.rejected is not None
    assert response.rejected.code == "sync.entity_exists"
    assert response.acked_through == 1


def test_a_site_cannot_send_events_for_another_site(central_db: CentralDb) -> None:
    with pytest.raises(SiteMismatchError):
        central_db.push("S01", [_note_event(1, site_id=SITE_B)])
    with pytest.raises(SiteMismatchError):
        central_db.push("S01", [_note_event(1, company_id=uuid.uuid4())])
    assert central_db.count(InboxEvent) == 0


def test_unsorted_or_duplicated_batches_are_refused(central_db: CentralDb) -> None:
    with pytest.raises(InvalidBatchError):
        central_db.push("S01", [_note_event(2), _note_event(1)])
    with pytest.raises(InvalidBatchError):
        central_db.push("S01", [_note_event(1), _note_event(1)])


def test_sites_are_tracked_independently(central_db: CentralDb) -> None:
    central_db.push("S01", [_note_event(1), _note_event(2)])
    response = central_db.push("S02", [_note_event(1, site_id=SITE_B)])
    assert response.acked_through == 1
    assert central_db.count(InboxEvent) == 3


def test_the_three_dates_are_kept(
    central_db: CentralDb, site_a: SiteDb, site_clock: FakeClock, clock: FakeClock
) -> None:
    site_clock.advance(timedelta(days=2))  # horloge du site en avance de 2 jours
    events = _notes(site_a, 1)
    clock.advance(timedelta(hours=1))
    central_db.push("S01", events)
    with central_db.factory() as session:
        note = session.scalars(select(CentralDemoNote)).one()
    assert note.business_date == date(2026, 10, 20)  # date métier saisie sur le site
    assert note.occurred_at == site_clock.now()  # heure locale du site (indicative)
    assert note.received_at == clock.now()  # heure de réception au central


def test_every_known_event_type_has_a_central_handler() -> None:
    assert build_registry().event_types() == set(CENTRAL_HANDLERS)
