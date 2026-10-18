"""Plusieurs utilisateurs du même site saisissent en même temps : aucun trou, aucun doublon."""

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from nkap.core.orm import Actor
from nkap.site_node.audit_log import verify_audit_log
from nkap.site_node.demo_notes import create_demo_note, list_demo_notes
from nkap.site_node.models import OutboxEvent
from support.site import SiteDb

WORKERS = 8
NOTES_PER_WORKER = 25


def test_concurrent_writers_get_contiguous_site_seq(site_db: SiteDb) -> None:
    def write(worker: int) -> None:
        for i in range(NOTES_PER_WORKER):
            create_demo_note(site_db.uow, f"poste {worker} note {i}", actor=Actor.system())

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(write, range(WORKERS)))

    total = WORKERS * NOTES_PER_WORKER
    with site_db.factory() as session:
        seqs = list(session.scalars(select(OutboxEvent.site_seq).order_by(OutboxEvent.site_seq)))
        note_ids = set(
            session.scalars(
                select(OutboxEvent.entity_id).where(OutboxEvent.event_type == "DemoNoteCreated")
            )
        )
        audit = verify_audit_log(session)
    assert seqs == list(range(1, 2 * total + 1))  # une note = un événement + son audit
    notes = list_demo_notes(site_db.factory)
    assert len(notes) == total
    assert note_ids == {n.id for n in notes}
    assert audit.ok
    assert audit.checked == total
