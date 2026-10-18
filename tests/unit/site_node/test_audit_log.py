"""Journal d'audit du site : chaîné, en ajout seul, falsification détectée."""

import json
import uuid

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from nkap.audit.chain import GENESIS_HASH
from nkap.core.orm import Actor
from nkap.site_node.audit_log import verify_audit_log
from nkap.site_node.demo_notes import create_demo_note
from nkap.site_node.models import OutboxEvent, SiteAuditChainHead, SiteAuditLog
from support.site import SiteDb


def _entries(db: SiteDb) -> list[SiteAuditLog]:
    with db.factory() as session:
        return list(session.scalars(select(SiteAuditLog).order_by(SiteAuditLog.chain_seq)))


def _create_notes(db: SiteDb, count: int) -> None:
    for i in range(count):
        create_demo_note(db.uow, f"note {i}", actor=Actor.system())


def test_each_operation_adds_a_chained_audit_entry(site_db: SiteDb) -> None:
    _create_notes(site_db, 3)
    entries = _entries(site_db)
    assert [e.chain_seq for e in entries] == [1, 2, 3]
    assert entries[0].prev_hash == GENESIS_HASH
    assert entries[1].prev_hash == entries[0].hash
    assert entries[2].prev_hash == entries[1].hash
    assert {e.action for e in entries} == {"demo_note.create"}
    assert json.loads(entries[0].details) == {"business_date": "2026-10-18", "text": "note 0"}
    with site_db.factory() as session:
        result = verify_audit_log(session)
        head = session.get(SiteAuditChainHead, 1)
    assert result.ok
    assert result.checked == 3
    assert head is not None
    assert (head.last_seq, head.last_hash) == (3, entries[2].hash)


def test_replicated_audit_event_carries_the_same_hash(site_db: SiteDb) -> None:
    _create_notes(site_db, 1)
    [entry] = _entries(site_db)
    with site_db.factory() as session:
        payload = session.scalars(
            select(OutboxEvent.payload).where(OutboxEvent.event_type == "AuditEntryRecorded")
        ).one()
    replicated = json.loads(payload)
    assert replicated["hash"] == entry.hash
    assert replicated["prev_hash"] == entry.prev_hash
    assert replicated["chain_seq"] == entry.chain_seq


def test_audit_entries_cannot_be_modified_or_deleted(site_db: SiteDb) -> None:
    _create_notes(site_db, 2)
    with pytest.raises(DBAPIError, match="ajout seul"), site_db.factory.begin() as session:
        session.execute(update(SiteAuditLog).values(actor_label="pirate"))
    with pytest.raises(DBAPIError, match="ajout seul"), site_db.factory.begin() as session:
        session.execute(delete(SiteAuditLog))
    if site_db.engine.dialect.name == "postgresql":
        with pytest.raises(DBAPIError, match="ajout seul"), site_db.factory.begin() as session:
            session.execute(text("TRUNCATE audit_log"))
    assert len(_entries(site_db)) == 2


def test_the_database_refuses_an_entry_that_breaks_the_chain(site_db: SiteDb) -> None:
    _create_notes(site_db, 1)
    [first] = _entries(site_db)
    forged = {
        "chain_seq": 2,
        "audit_id": uuid.UUID("01900000-0000-7000-8000-0000000000ff"),
        "occurred_at": first.occurred_at,
        "actor_label": "pirate",
        "action": "demo_note.create",
        "details": "{}",
        "prev_hash": "f" * 64,  # ne pointe pas sur la ligne précédente
        "hash": "e" * 64,
    }
    with pytest.raises(DBAPIError, match="chainage"), site_db.factory.begin() as session:
        session.execute(SiteAuditLog.__table__.insert().values(**forged))


def test_the_chain_head_only_moves_forward(site_db: SiteDb) -> None:
    _create_notes(site_db, 2)
    with pytest.raises(DBAPIError, match="tete de chaine"), site_db.factory.begin() as session:
        session.execute(update(SiteAuditChainHead).values(last_seq=1))
    with pytest.raises(DBAPIError, match="tete de chaine"), site_db.factory.begin() as session:
        session.execute(delete(SiteAuditChainHead))


def test_tampering_with_protections_disabled_is_detected(site_db: SiteDb) -> None:
    """Un fraudeur qui contourne les protections de la base est quand même repéré (T23)."""
    _create_notes(site_db, 4)
    with site_db.engine.begin() as conn:
        if conn.dialect.name == "sqlite":
            conn.execute(text("DROP TRIGGER trg_audit_log_no_update"))
        else:
            conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        conn.execute(
            text("UPDATE audit_log SET details = :d WHERE chain_seq = 3"),
            {"d": '{"text":"falsifié"}'},
        )
    with site_db.factory() as session:
        result = verify_audit_log(session)
    assert not result.ok
    assert result.first_broken_seq == 3
    assert result.checked == 2
