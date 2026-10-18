"""Journal d'audit du site : ajout d'une ligne chaînée et vérification de la chaîne."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.orm import Session

from nkap.audit.chain import AuditContent, ChainVerification
from nkap.audit.store import AuditStore
from nkap.core.clock import Clock
from nkap.core.orm import Actor
from nkap.site_node.identity import NodeIdentity
from nkap.site_node.models import SiteAuditChainHead, SiteAuditLog

SITE_AUDIT = AuditStore(SiteAuditLog, SiteAuditChainHead)


def append_audit_entry(
    session: Session,
    *,
    clock: Clock,
    identity: NodeIdentity,
    actor: Actor,
    action: str,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    details: Mapping[str, object] | None = None,
) -> tuple[AuditContent, str]:
    """Ajoute une ligne au journal du site. Renvoie (contenu, empreinte)."""
    return SITE_AUDIT.append(
        session,
        clock=clock,
        site_id=identity.site_id,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )


def verify_audit_log(session: Session) -> ChainVerification:
    """Vérifie l'intégrité complète du journal d'audit du site."""
    return SITE_AUDIT.verify(session)
