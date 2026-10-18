"""Journal d'audit du site : ajout d'une ligne chaînée et vérification de la chaîne."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from nkap.audit.chain import AuditContent, ChainVerification, normalize_details, verify_chain
from nkap.core.canonical import canonical_json
from nkap.core.clock import Clock
from nkap.core.ids import uuid7
from nkap.core.orm import Actor
from nkap.site_node.identity import NodeIdentity
from nkap.site_node.models import SiteAuditChainHead, SiteAuditLog


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
    """Ajoute une ligne au journal, chaînée sur la précédente. Renvoie (contenu, empreinte)."""
    head = session.execute(
        select(SiteAuditChainHead).where(SiteAuditChainHead.id == 1).with_for_update()
    ).scalar_one()
    content = AuditContent(
        chain_seq=head.last_seq + 1,
        audit_id=uuid7(clock),
        occurred_at=clock.now(),
        site_id=identity.site_id,
        actor_id=actor.user_id,
        actor_label=actor.label,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=normalize_details(details),
        prev_hash=head.last_hash,
    )
    digest = content.compute_hash()
    session.add(
        SiteAuditLog(
            chain_seq=content.chain_seq,
            audit_id=content.audit_id,
            occurred_at=content.occurred_at,
            site_id=content.site_id,
            actor_id=content.actor_id,
            actor_label=content.actor_label,
            action=content.action,
            entity_type=content.entity_type,
            entity_id=content.entity_id,
            details=canonical_json(content.details),
            prev_hash=content.prev_hash,
            hash=digest,
        )
    )
    # La ligne doit exister avant de déplacer la tête de chaîne (contrôlé en base).
    session.flush()
    head.last_seq = content.chain_seq
    head.last_hash = digest
    session.flush()
    return content, digest


def verify_audit_log(session: Session) -> ChainVerification:
    """Relit tout le journal et vérifie la chaîne, puis la cohérence de la tête de chaîne."""
    rows = session.scalars(
        select(SiteAuditLog).order_by(SiteAuditLog.chain_seq).execution_options(yield_per=1000)
    )
    try:
        result = verify_chain((row.content(), row.hash) for row in rows)
    finally:
        rows.close()  # la vérification peut s'arrêter avant la fin : on libère le curseur
    if not result.ok:
        return result
    head = session.get(SiteAuditChainHead, 1)
    if head is None or head.last_seq != result.checked:
        return ChainVerification(False, result.checked, result.checked + 1, "tête de chaîne")
    if result.checked:
        last = session.get(SiteAuditLog, head.last_seq)
        if last is None or last.hash != head.last_hash:
            return ChainVerification(False, result.checked, head.last_seq, "tête de chaîne")
    return result
