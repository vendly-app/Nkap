"""Colonnes communes des journaux d'audit (base du site et base centrale)."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from nkap.audit.chain import AuditContent, normalize_details
from nkap.core.db_types import UTCDateTime


class AuditLogMixin:
    """Une ligne du journal. Ajout seul : modification et suppression refusées en base."""

    chain_seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    audit_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    site_id: Mapped[UUID | None] = mapped_column(Uuid)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    actor_label: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[UUID | None] = mapped_column(Uuid)
    details: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)

    def content(self) -> AuditContent:
        return AuditContent(
            chain_seq=self.chain_seq,
            audit_id=self.audit_id,
            occurred_at=self.occurred_at,
            site_id=self.site_id,
            actor_id=self.actor_id,
            actor_label=self.actor_label,
            action=self.action,
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            details=normalize_details(json.loads(self.details)),
            prev_hash=self.prev_hash,
        )


class AuditChainHeadMixin:
    """Tête de chaîne : dernier numéro et dernière empreinte (une seule ligne)."""

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    last_seq: Mapped[int] = mapped_column(BigInteger)
    last_hash: Mapped[str] = mapped_column(String(64))
