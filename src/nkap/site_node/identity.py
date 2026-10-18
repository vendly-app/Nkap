"""Identité du nœud de site (société, site, code, fuseau horaire).

Elle est écrite **une seule fois**, à l'installation, et ne change plus : tous les
événements produits par ce site portent cet identifiant de site. Une base ne peut donc
pas être « réutilisée » pour un autre site par erreur.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from nkap.core.errors import NkapError
from nkap.core.orm import SITE_CODE_PATTERN
from nkap.site_node.models import NodeIdentityRow

DEFAULT_TIMEZONE = "Africa/Douala"


class NodeNotInitializedError(NkapError):
    default_code = "site.not_initialized"
    http_status = 503


class NodeIdentityMismatchError(NkapError):
    default_code = "site.identity_mismatch"
    http_status = 409


@dataclass(frozen=True, slots=True)
class NodeIdentity:
    company_id: UUID
    site_id: UUID
    site_code: str
    timezone: str = DEFAULT_TIMEZONE

    def __post_init__(self) -> None:
        if not SITE_CODE_PATTERN.match(self.site_code):
            raise ValueError(
                f"Code de site invalide : {self.site_code!r} "
                "(2 à 8 lettres majuscules ou chiffres)."
            )
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Fuseau horaire inconnu : {self.timezone!r}.") from exc


def load_identity(session: Session) -> NodeIdentity:
    row = session.get(NodeIdentityRow, 1)
    if row is None:
        raise NodeNotInitializedError()
    return NodeIdentity(row.company_id, row.site_id, row.site_code, row.timezone)


def initialize_identity(session: Session, identity: NodeIdentity, now: datetime) -> NodeIdentity:
    """Enregistre l'identité du site ; sans effet si elle est déjà enregistrée à l'identique."""
    existing = session.get(NodeIdentityRow, 1)
    if existing is not None:
        current = NodeIdentity(
            existing.company_id, existing.site_id, existing.site_code, existing.timezone
        )
        if current != identity:
            raise NodeIdentityMismatchError(site_code=current.site_code)
        return current
    session.add(
        NodeIdentityRow(
            id=1,
            company_id=identity.company_id,
            site_id=identity.site_id,
            site_code=identity.site_code,
            timezone=identity.timezone,
            created_at=now,
        )
    )
    return identity
