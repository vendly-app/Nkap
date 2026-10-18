import uuid

import pytest
from sqlalchemy import select

from nkap.central.audit_log import CENTRAL_AUDIT
from nkap.central.auth import (
    TOKEN_PREFIX,
    SiteAlreadyRegisteredError,
    SiteAuthError,
    authenticate,
    hash_token,
    register_site,
    revoke_site,
)
from nkap.central.models import CentralAuditLog, SyncSite
from nkap.core.clock import FakeClock
from nkap.core.orm import Actor
from support.central import CentralDb
from support.events import COMPANY_ID, SITE_A

ADMIN = Actor(user_id=None, label="admin")


def test_tokens_are_random_and_stored_only_as_a_hash(central_db: CentralDb) -> None:
    token = central_db.tokens["S01"]
    assert token.startswith(TOKEN_PREFIX)
    assert len(token) > 40
    assert token != central_db.tokens["S02"]
    with central_db.factory() as session:
        stored = session.scalars(select(SyncSite.token_hash)).all()
    assert token not in stored
    assert hash_token(token) in stored


def test_authenticate_returns_the_site_behind_a_token(central_db: CentralDb) -> None:
    with central_db.factory() as session:
        site = authenticate(session, central_db.tokens["S01"])
        assert (site.site_id, site.company_id, site.site_code) == (SITE_A, COMPANY_ID, "S01")
        for bad in (None, "", "nks_inconnu", central_db.tokens["S01"][4:]):
            with pytest.raises(SiteAuthError):
                authenticate(session, bad)


def test_a_site_or_a_code_cannot_be_registered_twice(
    central_db: CentralDb, clock: FakeClock
) -> None:
    with pytest.raises(SiteAlreadyRegisteredError), central_db.factory.begin() as session:
        register_site(
            session,
            site_id=uuid.uuid4(),
            company_id=COMPANY_ID,
            site_code="S01",
            clock=clock,
            actor=ADMIN,
        )
    with pytest.raises(ValueError, match="invalide"), central_db.factory.begin() as session:
        register_site(
            session,
            site_id=uuid.uuid4(),
            company_id=COMPANY_ID,
            site_code="mauvais code",
            clock=clock,
            actor=ADMIN,
        )


def test_revocation_blocks_the_site_and_is_audited(central_db: CentralDb, clock: FakeClock) -> None:
    with central_db.factory.begin() as session:
        revoke_site(session, site_id=SITE_A, clock=clock, actor=ADMIN)
    with central_db.factory() as session:
        with pytest.raises(SiteAuthError):
            authenticate(session, central_db.tokens["S01"])
        actions = list(
            session.scalars(select(CentralAuditLog.action).order_by(CentralAuditLog.chain_seq))
        )
        assert actions == ["sync_site.register", "sync_site.register", "sync_site.revoke"]
        assert CENTRAL_AUDIT.verify(session).ok
