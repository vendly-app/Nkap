"""Banc de simulation multi-sites.

Un central (SQLite ou PostgreSQL) et plusieurs nœuds de site (SQLite), chacun avec :

- sa propre horloge (qu'on peut avancer, reculer, décaler) ;
- sa propre liaison réseau (qu'on peut couper, ou qui peut « perdre » des réponses) ;
- son propre envoi de synchronisation, qui passe par la vraie API HTTP du central.

``assert_converged()`` vérifie les invariants de bout en bout : tout ce qui a été saisi sur
les sites est au central, une seule fois, et les journaux d'audit sont identiques.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType

from fastapi.testclient import TestClient
from sqlalchemy import URL, select

from nkap.central.api import create_central_app
from nkap.central.auth import AuthenticatedSite, register_site
from nkap.central.models import CentralDemoNote, InboxEvent, SiteAuditEntry, SyncSiteState
from nkap.core.clock import FakeClock
from nkap.core.orm import Actor
from nkap.site_node.audit_log import verify_audit_log
from nkap.site_node.demo_notes import create_demo_note, list_demo_notes
from nkap.site_node.gateway import HttpCentralGateway
from nkap.site_node.identity import NodeIdentity
from nkap.site_node.models import OUTBOX_ACKED, DemoNote, OutboxEvent, SiteAuditLog
from nkap.site_node.sync_sender import SyncRunResult, SyncSender
from nkap.site_node.sync_status import SyncStatusView, read_sync_status
from support.central import CentralDb, open_central_db
from support.db import sqlite_url
from support.events import COMPANY_ID
from support.network import LinkedGateway, NetworkLink
from support.site import SiteDb, open_site_db

START = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)


@dataclass
class SimSite:
    code: str
    site_id: uuid.UUID
    db: SiteDb
    clock: FakeClock
    link: NetworkLink
    sender: SyncSender

    def create_notes(self, count: int, prefix: str = "note") -> list[DemoNote]:
        return [
            create_demo_note(self.db.uow, f"{self.code} {prefix} {i}", actor=Actor.system())
            for i in range(count)
        ]

    def sync(self) -> SyncRunResult:
        return self.sender.sync_once(force=True)

    def go_offline(self) -> None:
        self.link.online = False

    def go_online(self) -> None:
        self.link.online = True

    def status(self) -> SyncStatusView:
        with self.db.factory() as session:
            return read_sync_status(session, self.clock)

    def notes(self) -> list[DemoNote]:
        return list_demo_notes(self.db.factory)


@dataclass
class Bench:
    tmp_path: Path
    central_url: URL | None = None
    central_clock: FakeClock = field(default_factory=lambda: FakeClock(START))
    sites: dict[str, SimSite] = field(default_factory=dict)

    def __post_init__(self) -> None:
        url = self.central_url or sqlite_url(self.tmp_path / "central.db")
        self.central: CentralDb = open_central_db(url, self.central_clock, sites=())
        self.client = TestClient(create_central_app(self.central.factory, clock=self.central_clock))
        self.client.__enter__()

    # --- Construction ---------------------------------------------------------------

    def add_site(self, code: str) -> SimSite:
        site_id = uuid.uuid4()
        with self.central.factory.begin() as session:
            token = register_site(
                session,
                site_id=site_id,
                company_id=COMPANY_ID,
                site_code=code,
                clock=self.central_clock,
                actor=Actor.system(),
            )
        self.central.tokens[code] = token
        self.central.sites[code] = AuthenticatedSite(site_id, COMPANY_ID, code)

        clock = FakeClock(START)
        identity = NodeIdentity(company_id=COMPANY_ID, site_id=site_id, site_code=code)
        db = open_site_db(sqlite_url(self.tmp_path / f"site_{code}.db"), clock, identity)
        link = NetworkLink()
        gateway = LinkedGateway(HttpCentralGateway(self.client, token), link)
        sender = SyncSender(db.factory, gateway, clock, rng=random.Random(len(self.sites)))
        site = SimSite(code, site_id, db, clock, link, sender)
        self.sites[code] = site
        return site

    def __enter__(self) -> Bench:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.client.__exit__(None, None, None)
        for site in self.sites.values():
            site.db.close()
        self.central.close()

    # --- Actions ---------------------------------------------------------------------

    def sync_all(self, rounds: int = 3) -> None:
        """Chaque site tente de se synchroniser (ceux qui sont coupés échouent, comme en vrai)."""
        for _ in range(rounds):
            for site in self.sites.values():
                site.sync()

    def advance(self, delta: timedelta) -> None:
        self.central_clock.advance(delta)
        for site in self.sites.values():
            site.clock.advance(delta)

    # --- Invariants ------------------------------------------------------------------

    def assert_converged(self) -> None:
        """Tout est au central, une seule fois, dans l'ordre, et les journaux concordent."""
        with self.central.factory() as central:
            central_notes = {n.id: n for n in central.scalars(select(CentralDemoNote))}
            for site in self.sites.values():
                with site.db.factory() as local:
                    rows = list(local.scalars(select(OutboxEvent).order_by(OutboxEvent.site_seq)))
                    assert [r.site_seq for r in rows] == list(range(1, len(rows) + 1))
                    assert {r.status for r in rows} <= {OUTBOX_ACKED}, f"{site.code} non acquitté"
                    assert verify_audit_log(local).ok
                    local_audit = list(
                        local.scalars(select(SiteAuditLog).order_by(SiteAuditLog.chain_seq))
                    )
                    notes = list(local.scalars(select(DemoNote)))

                state = central.get(SyncSiteState, site.site_id)
                assert state is not None
                assert state.last_seq == len(rows), f"{site.code} : numéros reçus"
                received = list(
                    central.scalars(
                        select(InboxEvent)
                        .where(InboxEvent.site_id == site.site_id)
                        .order_by(InboxEvent.site_seq)
                    )
                )
                assert [e.event_id for e in received] == [r.event_id for r in rows]
                assert [e.fingerprint for e in received] == [r.fingerprint for r in rows]

                central_audit = list(
                    central.scalars(
                        select(SiteAuditEntry)
                        .where(SiteAuditEntry.site_id == site.site_id)
                        .order_by(SiteAuditEntry.chain_seq)
                    )
                )
                assert [a.hash for a in central_audit] == [a.hash for a in local_audit]

                for note in notes:
                    assert note.sync_status == "synced"
                    copy = central_notes.pop(note.id)
                    assert (copy.text, copy.site_id) == (note.text, site.site_id)
            assert central_notes == {}, "notes au central inconnues des sites"

    def central_note_count(self) -> int:
        return self.central.count(CentralDemoNote)
