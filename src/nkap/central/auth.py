"""Authentification des nœuds de site auprès du central.

Chaque site reçoit, à son enregistrement, un **jeton secret** long et aléatoire. Le central
n'en garde que l'empreinte SHA-256 : une fuite de la base centrale ne révèle pas les jetons.
Le site présente son jeton à chaque envoi (en-tête ``Authorization: Bearer ...``).

L'identifiant du site vient du jeton, jamais du contenu envoyé : un site ne peut donc pas
envoyer d'événements au nom d'un autre (décision 002).

Étape 2 : ce mécanisme deviendra le « compte technique de synchronisation » du site,
avec des jetons de courte durée renouvelés automatiquement.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from nkap.audit.chain import GENESIS_HASH
from nkap.central.audit_log import CENTRAL_AUDIT
from nkap.central.models import SyncSite, SyncSiteState
from nkap.core.canonical import sha256_hex
from nkap.core.clock import Clock
from nkap.core.errors import NkapError
from nkap.core.orm import SITE_CODE_PATTERN, Actor

TOKEN_PREFIX = "nks_"  # noqa: S105 - préfixe public des jetons, pas un secret


class SiteAuthError(NkapError):
    default_code = "auth.invalid_site_token"
    http_status = 401


class SiteAlreadyRegisteredError(NkapError):
    default_code = "auth.site_already_registered"
    http_status = 409


@dataclass(frozen=True, slots=True)
class AuthenticatedSite:
    site_id: UUID
    company_id: UUID
    site_code: str


def hash_token(token: str) -> str:
    return sha256_hex(token)


def register_site(
    session: Session,
    *,
    site_id: UUID,
    company_id: UUID,
    site_code: str,
    clock: Clock,
    actor: Actor,
) -> str:
    """Autorise un site et renvoie son jeton. Le jeton n'est affiché qu'une seule fois."""
    if not SITE_CODE_PATTERN.match(site_code):
        raise ValueError(f"Code de site invalide : {site_code!r}.")
    duplicate = session.scalar(
        select(SyncSite).where((SyncSite.site_id == site_id) | (SyncSite.site_code == site_code))
    )
    if duplicate is not None:
        raise SiteAlreadyRegisteredError(site_code=site_code)
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    session.add(
        SyncSite(
            site_id=site_id,
            company_id=company_id,
            site_code=site_code,
            token_hash=hash_token(token),
            active=True,
            registered_at=clock.now(),
        )
    )
    session.flush()
    session.add(
        SyncSiteState(
            site_id=site_id,
            last_seq=0,
            last_received_at=None,
            audit_last_seq=0,
            audit_last_hash=GENESIS_HASH,
        )
    )
    CENTRAL_AUDIT.append(
        session,
        clock=clock,
        site_id=None,
        actor=actor,
        action="sync_site.register",
        entity_type="sync_site",
        entity_id=site_id,
        details={"site_code": site_code, "company_id": company_id},
    )
    return token


def revoke_site(session: Session, *, site_id: UUID, clock: Clock, actor: Actor) -> None:
    """Retire à un site le droit de se synchroniser (jeton volé, site fermé...)."""
    site = session.get(SyncSite, site_id)
    if site is None:
        raise SiteAuthError()
    site.active = False
    CENTRAL_AUDIT.append(
        session,
        clock=clock,
        site_id=None,
        actor=actor,
        action="sync_site.revoke",
        entity_type="sync_site",
        entity_id=site_id,
        details={"site_code": site.site_code},
    )


def authenticate(session: Session, token: str | None) -> AuthenticatedSite:
    """Retrouve le site correspondant à un jeton, ou refuse."""
    if not token or not token.startswith(TOKEN_PREFIX):
        raise SiteAuthError()
    site = session.scalar(select(SyncSite).where(SyncSite.token_hash == hash_token(token)))
    if site is None or not site.active:
        raise SiteAuthError()
    return AuthenticatedSite(site.site_id, site.company_id, site.site_code)
