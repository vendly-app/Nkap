"""Une opération et son événement sont écrits ensemble, ou pas du tout."""

import json
from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError

from nkap.core.clock import FakeClock
from nkap.core.orm import Actor
from nkap.events.catalog import DEMO_NOTE_CREATED, AuditEntryRecordedV1, DemoNoteCreatedV1
from nkap.site_node.demo_notes import create_demo_note, list_demo_notes
from nkap.site_node.models import OUTBOX_ACKED, DemoNote, OutboxEvent
from nkap.site_node.outbox import OutboxCorruptedError, envelope_from_outbox_row
from nkap.site_node.sequences import SYNC_SEQUENCE, current_value
from nkap.site_node.unit_of_work import MissingAuditError
from support.events import COMPANY_ID, SITE_A
from support.site import SiteDb

SYSTEM = Actor.system()


def _outbox(db: SiteDb) -> list[OutboxEvent]:
    with db.factory() as session:
        return list(session.scalars(select(OutboxEvent).order_by(OutboxEvent.site_seq)))


def test_creating_a_note_writes_the_note_and_its_event(site_db: SiteDb) -> None:
    note = create_demo_note(site_db.uow, "  Livraison de farine  ", actor=SYSTEM)
    assert note.text == "Livraison de farine"
    assert note.sync_status == "pending"
    assert note.business_date == date(2026, 10, 18)  # date du jour à Douala

    row, audit_row = _outbox(site_db)
    assert row.site_seq == 1
    assert row.status == "pending"
    assert row.attempts == 0
    envelope = envelope_from_outbox_row(row)
    assert envelope.event_type == "DemoNoteCreated"
    assert envelope.entity_id == note.id
    assert envelope.site_id == SITE_A
    assert envelope.company_id == COMPANY_ID
    assert envelope.business_date == note.business_date
    assert envelope.payload == {"text": "Livraison de farine"}
    assert json.loads(row.payload) == envelope.payload

    # Même transaction : la ligne d'audit, répliquée par un second événement.
    audit = envelope_from_outbox_row(audit_row)
    assert audit.event_type == "AuditEntryRecorded"
    assert audit.site_seq == 2
    assert audit.tx_id == envelope.tx_id
    assert envelope.tx_size == audit.tx_size == 2
    assert audit.payload["action"] == "demo_note.create"
    assert audit.payload["entity_id"] == str(note.id)


def test_site_seq_is_contiguous_without_gaps(site_db: SiteDb) -> None:
    for i in range(5):
        create_demo_note(site_db.uow, f"note {i}", actor=SYSTEM)
    assert [row.site_seq for row in _outbox(site_db)] == list(range(1, 11))
    with site_db.factory() as session:
        assert current_value(session, SYNC_SEQUENCE) == 10


def test_a_failed_operation_leaves_no_trace(site_db: SiteDb) -> None:
    create_demo_note(site_db.uow, "avant", actor=SYSTEM)

    class Boom(Exception):
        pass

    def fail_after_emit() -> None:
        with site_db.uow.begin(SYSTEM) as tx:
            tx.emit(
                DEMO_NOTE_CREATED,
                entity_id=tx.new_id(),
                entity_version=1,
                payload=DemoNoteCreatedV1(text="jamais"),
            )
            raise Boom

    with pytest.raises(Boom):
        fail_after_emit()

    assert [n.text for n in list_demo_notes(site_db.factory)] == ["avant"]
    assert [row.site_seq for row in _outbox(site_db)] == [1, 2]
    with site_db.factory() as session:
        assert current_value(session, SYNC_SEQUENCE) == 2  # numéros 3 et 4 non consommés
    create_demo_note(site_db.uow, "après", actor=SYSTEM)
    assert [row.site_seq for row in _outbox(site_db)] == [1, 2, 3, 4]


def test_invalid_text_is_refused_before_any_write(site_db: SiteDb) -> None:
    with pytest.raises(ValidationError):
        create_demo_note(site_db.uow, "   ", actor=SYSTEM)
    assert _outbox(site_db) == []
    assert list_demo_notes(site_db.factory) == []


def test_several_events_of_one_transaction_share_tx_id(site_db: SiteDb) -> None:
    with site_db.uow.begin(SYSTEM) as tx:
        for text in ("un", "deux", "trois"):
            tx.emit(
                DEMO_NOTE_CREATED,
                entity_id=tx.new_id(),
                entity_version=1,
                payload=DemoNoteCreatedV1(text=text),
            )
        tx.audit("demo_note.bulk_create", details={"count": 3})
    envelopes = [envelope_from_outbox_row(row) for row in _outbox(site_db)]
    assert [e.site_seq for e in envelopes] == [1, 2, 3, 4]
    assert len({e.tx_id for e in envelopes}) == 1
    assert {e.tx_size for e in envelopes} == {4}


def test_a_business_event_without_audit_is_refused(site_db: SiteDb) -> None:
    def forget_audit() -> None:
        with site_db.uow.begin(SYSTEM) as tx:
            tx.emit(
                DEMO_NOTE_CREATED,
                entity_id=tx.new_id(),
                entity_version=1,
                payload=DemoNoteCreatedV1(text="sans trace"),
            )

    with pytest.raises(MissingAuditError):
        forget_audit()
    assert _outbox(site_db) == []


def test_emit_checks_the_payload_type_and_the_transaction_state(site_db: SiteDb) -> None:
    with pytest.raises(TypeError), site_db.uow.begin(SYSTEM) as tx:
        tx.emit(
            DEMO_NOTE_CREATED,
            entity_id=tx.new_id(),
            entity_version=1,
            payload=AuditEntryRecordedV1.model_construct(),
        )
    with site_db.uow.begin(SYSTEM) as tx:
        pass
    with pytest.raises(RuntimeError, match="terminée"):
        tx.emit(
            DEMO_NOTE_CREATED,
            entity_id=tx.new_id(),
            entity_version=1,
            payload=DemoNoteCreatedV1(text="trop tard"),
        )


def test_event_content_cannot_be_modified_in_the_database(site_db: SiteDb) -> None:
    create_demo_note(site_db.uow, "original", actor=SYSTEM)
    with pytest.raises(DBAPIError, match="immuable"), site_db.factory.begin() as session:
        session.execute(update(OutboxEvent).values(payload='{"text":"falsifié"}'))
    with pytest.raises(DBAPIError, match="immuable"), site_db.factory.begin() as session:
        session.execute(update(OutboxEvent).values(site_seq=99))


def test_unacknowledged_events_cannot_be_deleted(site_db: SiteDb) -> None:
    create_demo_note(site_db.uow, "à envoyer", actor=SYSTEM)
    with pytest.raises(DBAPIError, match="supprime"), site_db.factory.begin() as session:
        session.execute(delete(OutboxEvent))
    # Les colonnes de suivi restent modifiables, et un événement acquitté peut être purgé.
    with site_db.factory.begin() as session:
        session.execute(update(OutboxEvent).values(status=OUTBOX_ACKED, attempts=1))
    with site_db.factory.begin() as session:
        session.execute(delete(OutboxEvent))
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0


def test_a_tampered_outbox_row_is_detected(site_db: SiteDb) -> None:
    create_demo_note(site_db.uow, "original", actor=SYSTEM)
    row = _outbox(site_db)[0]
    row.payload = '{"text":"falsifié"}'  # modification en mémoire uniquement
    with pytest.raises(OutboxCorruptedError) as exc_info:
        envelope_from_outbox_row(row)
    assert exc_info.value.code == "sync.outbox_corrupted"


def test_notes_are_listed_in_creation_order(site_db: SiteDb, clock: FakeClock) -> None:
    for text in ("a", "b", "c"):
        create_demo_note(site_db.uow, text, actor=SYSTEM)
        clock.advance(timedelta(seconds=1))
    assert [n.text for n in list_demo_notes(site_db.factory)] == ["a", "b", "c"]
    with site_db.factory() as session:
        assert session.scalar(select(func.count()).select_from(DemoNote)) == 3
