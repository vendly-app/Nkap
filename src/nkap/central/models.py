"""Tables de la base centrale.

- ``sync_sites`` : sites autorisés à se synchroniser (avec l'empreinte de leur jeton).
- ``sync_site_states`` : où en est chaque site (dernier numéro reçu sans trou, audit).
- ``sync_inbox`` : tous les événements reçus, en ajout seul. C'est le journal qui fait foi.
- ``demo_notes`` : vue consolidée des notes factices de tous les sites.
- ``site_audit_entries`` : copie des journaux d'audit des sites, en ajout seul.
- ``audit_log`` / ``audit_chain_head`` : journal d'audit des actions faites au central.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from nkap.audit.models import AuditChainHeadMixin, AuditLogMixin
from nkap.core.db_types import UTCDateTime
from nkap.core.orm import make_metadata


class CentralBase(DeclarativeBase):
    metadata = make_metadata()


class SyncSite(CentralBase):
    """Site autorisé à envoyer des événements. Le jeton n'est jamais stocké en clair."""

    __tablename__ = "sync_sites"

    site_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid)
    site_code: Mapped[str] = mapped_column(String(16), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean)
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SyncSiteState(CentralBase):
    """Avancement de la synchronisation d'un site."""

    __tablename__ = "sync_site_states"
    __table_args__ = (
        CheckConstraint("last_seq >= 0", name="last_seq_non_negative"),
        CheckConstraint("audit_last_seq >= 0", name="audit_last_seq_non_negative"),
    )

    site_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("sync_sites.site_id"), primary_key=True)
    last_seq: Mapped[int] = mapped_column(BigInteger)
    last_received_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    audit_last_seq: Mapped[int] = mapped_column(BigInteger)
    audit_last_hash: Mapped[str] = mapped_column(String(64))


class InboxEvent(CentralBase):
    """Un événement reçu d'un site et appliqué. Ajout seul (protégé en base)."""

    __tablename__ = "sync_inbox"
    __table_args__ = (
        UniqueConstraint("site_id", "site_seq", name="uq_sync_inbox_site_seq"),
        Index("ix_sync_inbox_entity", "entity_type", "entity_id"),
    )

    event_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    site_id: Mapped[UUID] = mapped_column(Uuid)
    site_seq: Mapped[int] = mapped_column(BigInteger)
    tx_id: Mapped[UUID] = mapped_column(Uuid)
    tx_size: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    payload_version: Mapped[int] = mapped_column(Integer)
    company_id: Mapped[UUID] = mapped_column(Uuid)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[UUID] = mapped_column(Uuid)
    entity_version: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    business_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[UUID | None] = mapped_column(Uuid)
    payload: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)


class CentralDemoNote(CentralBase):
    """Note factice consolidée (une ligne par note, tous sites confondus)."""

    __tablename__ = "demo_notes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid)
    site_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    text: Mapped[str] = mapped_column(String(500))
    business_date: Mapped[date | None] = mapped_column(Date)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_by: Mapped[UUID | None] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    source_event_id: Mapped[UUID] = mapped_column(Uuid)


class SiteAuditEntry(CentralBase):
    """Copie d'une ligne du journal d'audit d'un site. Ajout seul (protégé en base)."""

    __tablename__ = "site_audit_entries"

    site_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    chain_seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    audit_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid)
    actor_label: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[UUID | None] = mapped_column(Uuid)
    details: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)


class CentralAuditLog(AuditLogMixin, CentralBase):
    """Journal d'audit des actions faites au central (ajout seul, chaîné)."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)


class CentralAuditChainHead(AuditChainHeadMixin, CentralBase):
    __tablename__ = "audit_chain_head"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)
