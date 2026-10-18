"""Base centrale prête à l'emploi pour les tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import URL, Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from nkap.central.auth import AuthenticatedSite, register_site
from nkap.central.handlers import CENTRAL_HANDLERS
from nkap.central.ingest import SyncIngestor
from nkap.core.clock import Clock
from nkap.core.db import create_db_engine, make_session_factory
from nkap.core.migrations import CENTRAL_MIGRATIONS, upgrade_database
from nkap.core.orm import Actor
from nkap.events.catalog import build_registry
from nkap.events.envelope import EventEnvelope
from nkap.sync.protocol import PROTOCOL_VERSION, PushRequest, PushResponse
from support.events import COMPANY_ID, SITE_A, SITE_B

DEFAULT_SITES = (("S01", SITE_A), ("S02", SITE_B))


@dataclass
class CentralDb:
    url: URL
    engine: Engine
    factory: sessionmaker[Session]
    ingestor: SyncIngestor
    tokens: dict[str, str] = field(default_factory=dict)
    sites: dict[str, AuthenticatedSite] = field(default_factory=dict)

    def push(self, code: str, events: list[EventEnvelope]) -> PushResponse:
        site = self.sites[code]
        request = PushRequest(
            protocol_version=PROTOCOL_VERSION, site_id=site.site_id, events=events
        )
        return self.ingestor.ingest(site, request)

    def count(self, model: Any) -> int:
        with self.factory() as session:
            return int(session.scalar(select(func.count()).select_from(model)) or 0)

    def close(self) -> None:
        self.engine.dispose()


def open_central_db(
    url: URL,
    clock: Clock,
    sites: tuple[tuple[str, uuid.UUID], ...] = DEFAULT_SITES,
) -> CentralDb:
    upgrade_database(CENTRAL_MIGRATIONS, url)
    engine = create_db_engine(url)
    factory = make_session_factory(engine)
    db = CentralDb(
        url, engine, factory, SyncIngestor(factory, clock, build_registry(), CENTRAL_HANDLERS)
    )
    for code, site_id in sites:
        with factory.begin() as session:
            db.tokens[code] = register_site(
                session,
                site_id=site_id,
                company_id=COMPANY_ID,
                site_code=code,
                clock=clock,
                actor=Actor.system(),
            )
        db.sites[code] = AuthenticatedSite(site_id, COMPANY_ID, code)
    return db
