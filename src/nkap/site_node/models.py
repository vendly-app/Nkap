"""Tables de la base d'un site.

- ``node_identity`` : qui est ce site (une seule ligne).
- ``site_sequences`` : compteurs locaux (``site_seq`` des événements, numéros lisibles).
- ``sync_outbox`` : file d'envoi des événements vers le central.
- ``demo_notes`` : données factices de l'étape 1 (une note = un texte).
- ``audit_log`` / ``audit_chain_head`` : journal d'audit chaîné et sa tête de chaîne.
- ``sync_state`` : état de la liaison avec le central (une seule ligne).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from nkap.audit.models import AuditChainHeadMixin, AuditLogMixin
from nkap.core.db_types import UTCDateTime
from nkap.core.orm import make_metadata

OUTBOX_PENDING = "pending"
OUTBOX_ACKED = "acked"
OUTBOX_REJECTED = "rejected"

SYNC_PENDING = "pending"
SYNC_SYNCED = "synced"
SYNC_ERROR = "error"


class SiteBase(DeclarativeBase):
    metadata = make_metadata()


class SyncTrackedMixin:
    """Donnée métier dont l'état de synchronisation est affiché à l'utilisateur.

    ``sync_status`` ne passe à « synced » qu'à réception de l'accusé du central
    (jamais avant : garde-fou du brief).
    """

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    sync_status: Mapped[str] = mapped_column(String(16))


class NodeIdentityRow(SiteBase):
    """Identité du site, écrite une fois à l'installation."""

    __tablename__ = "node_identity"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    company_id: Mapped[UUID] = mapped_column(Uuid)
    site_id: Mapped[UUID] = mapped_column(Uuid)
    site_code: Mapped[str] = mapped_column(String(16))
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SiteSequence(SiteBase):
    """Compteur local : dernière valeur attribuée."""

    __tablename__ = "site_sequences"
    __table_args__ = (CheckConstraint("last_value >= 0", name="non_negative"),)

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_value: Mapped[int] = mapped_column(BigInteger)


class OutboxEvent(SiteBase):
    """Un événement à envoyer (ou déjà envoyé) au central.

    Le contenu de l'événement est **immuable** (protégé par un déclencheur en base) ;
    seules les colonnes de suivi d'envoi (statut, tentatives, erreurs) évoluent.
    """

    __tablename__ = "sync_outbox"
    __table_args__ = (
        CheckConstraint("site_seq > 0", name="site_seq_positive"),
        CheckConstraint("tx_size > 0", name="tx_size_positive"),
        CheckConstraint("status IN ('pending', 'acked', 'rejected')", name="status_valid"),
        Index("ix_sync_outbox_status_seq", "status", "site_seq"),
        Index("ix_sync_outbox_entity", "entity_type", "entity_id"),
    )

    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    site_seq: Mapped[int] = mapped_column(BigInteger, unique=True)
    tx_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    tx_size: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    payload_version: Mapped[int] = mapped_column(Integer)
    company_id: Mapped[UUID] = mapped_column(Uuid)
    site_id: Mapped[UUID] = mapped_column(Uuid)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[UUID] = mapped_column(Uuid)
    entity_version: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    business_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[UUID | None] = mapped_column(Uuid)
    payload: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), server_default=OUTBOX_PENDING)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)


class DemoNote(SyncTrackedMixin, SiteBase):
    """Note factice (étape 1) : prouve la chaîne site → central sans métier réel."""

    __tablename__ = "demo_notes"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("sync_status IN ('pending', 'synced', 'error')", name="sync_status_valid"),
    )

    company_id: Mapped[UUID] = mapped_column(Uuid)
    site_id: Mapped[UUID] = mapped_column(Uuid)
    text: Mapped[str] = mapped_column(String(500))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[UUID | None] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)


class SiteAuditLog(AuditLogMixin, SiteBase):
    """Journal d'audit du site (ajout seul, chaîné, répliqué au central)."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)


class SiteAuditChainHead(AuditChainHeadMixin, SiteBase):
    __tablename__ = "audit_chain_head"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)


class SyncStateRow(SiteBase):
    """État de la synchronisation avec le central (affiché à l'écran Synchronisation)."""

    __tablename__ = "sync_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("consecutive_failures >= 0", name="failures_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    offline_since: Mapped[datetime | None] = mapped_column(UTCDateTime)
    consecutive_failures: Mapped[int] = mapped_column(Integer)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    central_acked_through: Mapped[int] = mapped_column(BigInteger)
    last_server_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    clock_offset_ms: Mapped[int | None] = mapped_column(BigInteger)


SYNCABLE_ENTITIES: dict[str, type[SyncTrackedMixin]] = {"demo_note": DemoNote}
"""Tables métier dont la colonne ``sync_status`` suit l'accusé de réception du central."""
