import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import URL

from nkap.core.clock import FakeClock
from nkap.core.orm import Actor
from nkap.site_node.demo_notes import create_demo_note
from nkap.site_node.identity import (
    NodeIdentity,
    NodeIdentityMismatchError,
    NodeNotInitializedError,
    initialize_identity,
    load_identity,
)
from support.site import SITE_A_IDENTITY, SiteDb, open_site_db


@pytest.fixture
def blank_site(db_url: URL, clock: FakeClock) -> Iterator[SiteDb]:
    db = open_site_db(db_url, clock, identity=None)
    yield db
    db.close()


def test_operations_are_refused_until_the_site_is_initialized(blank_site: SiteDb) -> None:
    with pytest.raises(NodeNotInitializedError) as exc_info:
        create_demo_note(blank_site.uow, "trop tôt", actor=Actor.system())
    assert "nkap-site init" in str(exc_info.value)


def test_identity_is_written_once_and_cannot_be_changed(
    blank_site: SiteDb, clock: FakeClock
) -> None:
    with blank_site.factory.begin() as session:
        initialize_identity(session, SITE_A_IDENTITY, clock.now())
    with blank_site.factory.begin() as session:  # même identité : sans effet
        initialize_identity(session, SITE_A_IDENTITY, clock.now())
    other = NodeIdentity(
        company_id=SITE_A_IDENTITY.company_id, site_id=uuid.uuid4(), site_code="S02"
    )
    with pytest.raises(NodeIdentityMismatchError), blank_site.factory.begin() as session:
        initialize_identity(session, other, clock.now())
    with blank_site.factory() as session:
        assert load_identity(session) == SITE_A_IDENTITY


@pytest.mark.parametrize(
    ("code", "timezone"),
    [
        ("s1", "Africa/Douala"),
        ("S", "Africa/Douala"),
        ("SITE-01", "Africa/Douala"),
        ("S01", "Mars"),
    ],
)
def test_invalid_identity_values_are_refused(code: str, timezone: str) -> None:
    with pytest.raises(ValueError, match=r"invalide|inconnu"):
        NodeIdentity(uuid.uuid4(), uuid.uuid4(), code, timezone)
