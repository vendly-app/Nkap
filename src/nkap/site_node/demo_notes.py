"""Notes factices (étape 1) : la plus petite opération qui traverse toute la chaîne.

Créer une note écrit, dans une seule transaction : la note, l'événement
``DemoNoteCreated`` dans l'outbox, la ligne d'audit et sa réplication (``AuditEntryRecorded``).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from nkap.core.clock import local_date
from nkap.core.orm import Actor
from nkap.events.catalog import DEMO_NOTE, DEMO_NOTE_CREATED, DemoNoteCreatedV1
from nkap.site_node.models import SYNC_PENDING, DemoNote
from nkap.site_node.unit_of_work import SiteUnitOfWork


def create_demo_note(
    uow: SiteUnitOfWork,
    text: str,
    *,
    actor: Actor,
    business_date: date | None = None,
) -> DemoNote:
    payload = DemoNoteCreatedV1(text=text)  # valide le texte avant toute écriture
    with uow.begin(actor) as tx:
        day = business_date or local_date(tx.clock, tx.identity.timezone)
        now = tx.now()
        note = DemoNote(
            id=tx.new_id(),
            company_id=tx.identity.company_id,
            site_id=tx.identity.site_id,
            text=payload.text,
            business_date=day,
            created_at=now,
            updated_at=now,
            created_by=actor.user_id,
            version=1,
            sync_status=SYNC_PENDING,
        )
        tx.session.add(note)
        tx.emit(
            DEMO_NOTE_CREATED,
            entity_id=note.id,
            entity_version=note.version,
            payload=payload,
            business_date=day,
        )
        tx.audit(
            "demo_note.create",
            entity_type=DEMO_NOTE,
            entity_id=note.id,
            details={"text": note.text, "business_date": day},
        )
    return note


def list_demo_notes(session_factory: sessionmaker[Session]) -> list[DemoNote]:
    with session_factory() as session:
        return list(session.scalars(select(DemoNote).order_by(DemoNote.created_at, DemoNote.id)))
