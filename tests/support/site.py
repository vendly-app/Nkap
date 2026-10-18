"""Bases de site prêtes à l'emploi pour les tests."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import URL, Engine
from sqlalchemy.orm import Session, sessionmaker

from nkap.core.clock import Clock
from nkap.core.db import create_db_engine, make_session_factory
from nkap.core.migrations import SITE_MIGRATIONS, upgrade_database
from nkap.site_node.identity import NodeIdentity, initialize_identity
from nkap.site_node.unit_of_work import SiteUnitOfWork
from support.events import COMPANY_ID, SITE_A

SITE_A_IDENTITY = NodeIdentity(company_id=COMPANY_ID, site_id=SITE_A, site_code="S01")


@dataclass
class SiteDb:
    url: URL
    engine: Engine
    factory: sessionmaker[Session]
    uow: SiteUnitOfWork

    def close(self) -> None:
        self.engine.dispose()


def open_site_db(
    url: URL,
    clock: Clock,
    identity: NodeIdentity | None = SITE_A_IDENTITY,
    *,
    migrate: bool = True,
) -> SiteDb:
    if migrate:
        upgrade_database(SITE_MIGRATIONS, url)
    engine = create_db_engine(url)
    factory = make_session_factory(engine)
    if identity is not None:
        with factory.begin() as session:
            initialize_identity(session, identity, clock.now())
    return SiteDb(url, engine, factory, SiteUnitOfWork(factory, clock))
