"""Assemblage du nœud de site à partir de sa configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import httpx2
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from nkap.core.clock import Clock, SystemClock
from nkap.core.db import create_db_engine, make_session_factory
from nkap.site_node.config import SiteSettings
from nkap.site_node.gateway import HttpCentralGateway, make_http_client
from nkap.site_node.sync_sender import SyncSender, SyncSettings
from nkap.site_node.unit_of_work import SiteUnitOfWork
from nkap.site_node.worker import SyncWorker


@dataclass
class SiteRuntime:
    settings: SiteSettings
    clock: Clock
    engine: Engine
    session_factory: sessionmaker[Session]
    uow: SiteUnitOfWork
    sender: SyncSender | None
    worker: SyncWorker | None
    http_client: httpx2.Client | None

    @property
    def drift_tolerance(self) -> timedelta:
        return timedelta(minutes=self.settings.clock_drift_tolerance_minutes)

    def close(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        if self.http_client is not None:
            self.http_client.close()
        self.engine.dispose()


def build_site_runtime(settings: SiteSettings, clock: Clock | None = None) -> SiteRuntime:
    clock = clock or SystemClock()
    engine = create_db_engine(settings.database_url)
    factory = make_session_factory(engine)
    sender = worker = client = None
    if settings.central_url and settings.sync_token:
        client = make_http_client(settings.central_url)
        gateway = HttpCentralGateway(client, settings.sync_token.get_secret_value())
        sender = SyncSender(
            factory,
            gateway,
            clock,
            SyncSettings(
                batch_size=settings.sync_batch_size,
                clock_drift_tolerance=timedelta(minutes=settings.clock_drift_tolerance_minutes),
            ),
        )
        worker = SyncWorker(sender, settings.sync_interval_seconds)
    return SiteRuntime(
        settings, clock, engine, factory, SiteUnitOfWork(factory, clock), sender, worker, client
    )
