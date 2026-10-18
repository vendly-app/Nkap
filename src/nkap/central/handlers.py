"""Application des événements reçus sur la base centrale.

Un « handler » par type d'événement. Il est appelé une seule fois par événement (les
doublons sont filtrés avant), dans l'ordre de ``site_seq``, à l'intérieur d'une transaction
qui couvre toute la transaction d'origine du site.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.orm import Session

from nkap.audit.chain import AuditContent, normalize_details
from nkap.central.auth import AuthenticatedSite
from nkap.central.models import CentralDemoNote, SiteAuditEntry
from nkap.core.canonical import canonical_json
from nkap.core.errors import NkapError
from nkap.events.catalog import AuditEntryRecordedV1, DemoNoteCreatedV1
from nkap.events.envelope import EventEnvelope


class EntityConflictError(NkapError):
    """L'objet existe déjà au central (même identifiant créé deux fois)."""

    default_code = "sync.entity_exists"


class AuditChainBrokenError(NkapError):
    """La ligne d'audit reçue ne prolonge pas la chaîne connue du central pour ce site."""

    default_code = "audit.chain_broken"


@dataclass
class ApplyContext:
    """Contexte d'application d'une transaction de site (modifiable par les handlers).

    Les valeurs ne sont recopiées dans l'état du site qu'après succès de toute la
    transaction : un échec ne laisse donc aucune trace.
    """

    now: datetime
    site: AuthenticatedSite
    audit_last_seq: int
    audit_last_hash: str


Handler = Callable[[Session, EventEnvelope, BaseModel, ApplyContext], None]


def apply_demo_note_created(
    session: Session, envelope: EventEnvelope, payload: BaseModel, ctx: ApplyContext
) -> None:
    if not isinstance(payload, DemoNoteCreatedV1):
        raise TypeError("Contenu inattendu pour DemoNoteCreated.")
    if session.get(CentralDemoNote, envelope.entity_id) is not None:
        raise EntityConflictError(entity_id=envelope.entity_id)
    session.add(
        CentralDemoNote(
            id=envelope.entity_id,
            company_id=envelope.company_id,
            site_id=envelope.site_id,
            text=payload.text,
            business_date=envelope.business_date,
            occurred_at=envelope.occurred_at,
            received_at=ctx.now,
            created_by=envelope.created_by,
            version=envelope.entity_version,
            source_event_id=envelope.event_id,
        )
    )


def apply_audit_entry_recorded(
    session: Session, envelope: EventEnvelope, payload: BaseModel, ctx: ApplyContext
) -> None:
    if not isinstance(payload, AuditEntryRecordedV1):
        raise TypeError("Contenu inattendu pour AuditEntryRecorded.")
    details = normalize_details(payload.details)
    content = AuditContent(
        chain_seq=payload.chain_seq,
        audit_id=envelope.entity_id,
        occurred_at=payload.occurred_at,
        site_id=envelope.site_id,
        actor_id=payload.actor_id,
        actor_label=payload.actor_label,
        action=payload.action,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        details=details,
        prev_hash=payload.prev_hash,
    )
    # Le central vérifie lui-même la chaîne : un journal réécrit sur le site est repéré.
    if (
        payload.chain_seq != ctx.audit_last_seq + 1
        or payload.prev_hash != ctx.audit_last_hash
        or content.compute_hash() != payload.hash
    ):
        raise AuditChainBrokenError(chain_seq=payload.chain_seq)
    session.add(
        SiteAuditEntry(
            site_id=envelope.site_id,
            chain_seq=payload.chain_seq,
            audit_id=envelope.entity_id,
            occurred_at=payload.occurred_at,
            actor_id=payload.actor_id,
            actor_label=payload.actor_label,
            action=payload.action,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            details=canonical_json(json.loads(canonical_json(details))),
            prev_hash=payload.prev_hash,
            hash=payload.hash,
            received_at=ctx.now,
        )
    )
    ctx.audit_last_seq = payload.chain_seq
    ctx.audit_last_hash = payload.hash


CENTRAL_HANDLERS: dict[str, Handler] = {
    "DemoNoteCreated": apply_demo_note_created,
    "AuditEntryRecorded": apply_audit_entry_recorded,
}
