"""Transaction métier du site : donnée + événement à envoyer, en un seul bloc.

C'est le cœur du « transactional outbox » : une opération (ex. créer une note) et
l'événement destiné au central sont écrits **dans la même transaction**. Soit les deux
existent, soit aucun : on ne peut pas perdre un événement, ni envoyer un événement
pour une opération qui n'a pas eu lieu.

Usage ::

    with uow.begin(actor) as tx:
        tx.session.add(note)
        tx.emit(DEMO_NOTE_CREATED, entity_id=note.id, entity_version=1, payload=payload)
    # à la sortie du bloc : événements numérotés, écrits dans l'outbox, puis validation.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from nkap.audit.chain import AuditContent
from nkap.core.canonical import to_jsonable
from nkap.core.clock import Clock
from nkap.core.ids import uuid7
from nkap.core.orm import Actor
from nkap.events.catalog import AUDIT_ENTRY_RECORDED, AuditEntryRecordedV1, build_registry
from nkap.events.envelope import EventEnvelope
from nkap.events.registry import EventDefinition, EventRegistry
from nkap.site_node.audit_log import append_audit_entry
from nkap.site_node.identity import NodeIdentity, load_identity
from nkap.site_node.outbox import outbox_row_from_envelope
from nkap.site_node.sequences import SYNC_SEQUENCE, allocate


class MissingAuditError(RuntimeError):
    """Erreur de programmation : une opération métier n'a pas été auditée."""


@dataclass(frozen=True, slots=True)
class _QueuedEvent:
    definition: EventDefinition
    entity_id: UUID
    entity_version: int
    payload: BaseModel
    business_date: date | None


class SiteTransaction:
    """Une transaction en cours sur la base du site."""

    def __init__(
        self,
        session: Session,
        identity: NodeIdentity,
        clock: Clock,
        actor: Actor,
        registry: EventRegistry,
    ) -> None:
        self.session = session
        self.identity = identity
        self.clock = clock
        self.actor = actor
        self._registry = registry
        self._queued: list[_QueuedEvent] = []
        self._closed = False
        self.envelopes: list[EventEnvelope] = []

    def now(self) -> datetime:
        return self.clock.now()

    def new_id(self) -> UUID:
        return uuid7(self.clock)

    def emit(
        self,
        definition: EventDefinition,
        *,
        entity_id: UUID,
        entity_version: int,
        payload: BaseModel,
        business_date: date | None = None,
    ) -> None:
        """Programme un événement, qui sera écrit dans l'outbox à la fin de la transaction."""
        if self._closed:
            raise RuntimeError("Transaction déjà terminée : impossible d'émettre un événement.")
        if not isinstance(payload, definition.payload_model):
            raise TypeError(
                f"Contenu attendu pour {definition.event_type} : "
                f"{definition.payload_model.__name__}, reçu : {type(payload).__name__}."
            )
        self._queued.append(
            _QueuedEvent(definition, entity_id, entity_version, payload, business_date)
        )

    def audit(
        self,
        action: str,
        *,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        details: Mapping[str, object] | None = None,
    ) -> AuditContent:
        """Ajoute une ligne au journal d'audit et programme sa réplication au central."""
        if self._closed:
            raise RuntimeError("Transaction déjà terminée : impossible d'auditer.")
        content, digest = append_audit_entry(
            self.session,
            clock=self.clock,
            identity=self.identity,
            actor=self.actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
        self.emit(
            AUDIT_ENTRY_RECORDED,
            entity_id=content.audit_id,
            entity_version=1,
            payload=AuditEntryRecordedV1(
                chain_seq=content.chain_seq,
                occurred_at=content.occurred_at,
                actor_id=content.actor_id,
                actor_label=content.actor_label,
                action=content.action,
                entity_type=content.entity_type,
                entity_id=content.entity_id,
                details=content.details,
                prev_hash=content.prev_hash,
                hash=digest,
            ),
        )
        return content

    def write_outbox(self) -> list[EventEnvelope]:
        """Numérote les événements programmés et les écrit dans l'outbox."""
        self._closed = True
        if not self._queued:
            return []
        business = [q for q in self._queued if q.definition is not AUDIT_ENTRY_RECORDED]
        if business and len(business) == len(self._queued):
            # Garde-fou : toute modification de données métier laisse une trace d'audit.
            raise MissingAuditError(
                "Opération métier sans ligne d'audit : appeler tx.audit() dans la transaction."
            )
        size = len(self._queued)
        sequence = allocate(self.session, SYNC_SEQUENCE, size)
        tx_id = uuid7(self.clock)
        occurred_at = self.clock.now()
        for site_seq, queued in zip(sequence, self._queued, strict=True):
            envelope = EventEnvelope(
                event_id=uuid7(self.clock),
                event_type=queued.definition.event_type,
                payload_version=queued.definition.payload_version,
                company_id=self.identity.company_id,
                site_id=self.identity.site_id,
                site_seq=site_seq,
                tx_id=tx_id,
                tx_size=size,
                entity_type=queued.definition.entity_type,
                entity_id=queued.entity_id,
                entity_version=queued.entity_version,
                occurred_at=occurred_at,
                business_date=queued.business_date,
                created_by=self.actor.user_id,
                payload=to_jsonable(queued.payload.model_dump()),
            )
            # Contrôle final : ce que le central recevra est conforme au catalogue.
            self._registry.parse_payload(envelope)
            self.session.add(outbox_row_from_envelope(envelope))
            self.envelopes.append(envelope)
        return self.envelopes


class SiteUnitOfWork:
    """Point d'entrée des opérations qui modifient la base du site."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        clock: Clock,
        registry: EventRegistry | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock
        self.registry = registry or build_registry()

    @contextmanager
    def begin(self, actor: Actor) -> Iterator[SiteTransaction]:
        with self.session_factory.begin() as session:
            tx = SiteTransaction(session, load_identity(session), self.clock, actor, self.registry)
            yield tx
            tx.write_outbox()
