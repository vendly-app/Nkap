"""Envoi des événements du site vers le central (site et central réels, liaison simulée)."""

import itertools
import random
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from nkap.central.api import create_central_app
from nkap.central.handlers import CENTRAL_HANDLERS, Handler
from nkap.central.models import CentralDemoNote, InboxEvent
from nkap.core.clock import FakeClock
from nkap.core.orm import Actor
from nkap.site_node.demo_notes import create_demo_note, list_demo_notes
from nkap.site_node.gateway import CentralUnavailableError, HttpCentralGateway
from nkap.site_node.models import OutboxEvent
from nkap.site_node.sync_sender import RunStatus, SyncSender, SyncSettings
from nkap.site_node.sync_status import SyncStatusView, read_sync_status
from nkap.site_node.worker import SyncWorker
from nkap.sync.protocol import PushRequest, PushResponse, SiteSyncState
from support.central import CentralDb, open_central_db
from support.db import sqlite_url
from support.network import LinkedGateway, NetworkLink
from support.site import SiteDb, open_site_db

START = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)


@dataclass
class Env:
    site: SiteDb
    central: CentralDb
    link: NetworkLink
    client: TestClient
    site_clock: FakeClock
    central_clock: FakeClock

    def sender(self, **settings: int) -> SyncSender:
        gateway = HttpCentralGateway(self.client, self.central.tokens["S01"])
        return SyncSender(
            self.site.factory,
            LinkedGateway(gateway, self.link),
            self.site_clock,
            SyncSettings(**settings),  # type: ignore[arg-type]
            rng=random.Random(0),  # aléa fixe : temporisations reproductibles
        )

    def notes(self, count: int) -> None:
        for i in range(count):
            create_demo_note(self.site.uow, f"note {i}", actor=Actor.system())

    def status(self) -> SyncStatusView:
        with self.site.factory() as session:
            return read_sync_status(session, self.site_clock)


def _make_env(tmp_path: Path, handlers: dict[str, Handler] | None = None) -> Iterator[Env]:
    site_clock, central_clock = FakeClock(START), FakeClock(START)
    site = open_site_db(sqlite_url(tmp_path / "site.db"), site_clock)
    central = open_central_db(sqlite_url(tmp_path / "central.db"), central_clock)
    app = create_central_app(central.factory, clock=central_clock, handlers=handlers)
    with TestClient(app) as client:
        yield Env(site, central, NetworkLink(), client, site_clock, central_clock)
    site.close()
    central.close()


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    yield from _make_env(tmp_path)


def test_pending_events_are_sent_acknowledged_and_marked_synced(env: Env) -> None:
    env.notes(3)
    assert {n.sync_status for n in list_demo_notes(env.site.factory)} == {"pending"}
    result = env.sender().sync_once()
    assert result.status is RunStatus.SYNCED
    assert (result.sent, result.acked, result.pending) == (6, 6, 0)
    assert {n.sync_status for n in list_demo_notes(env.site.factory)} == {"synced"}
    assert env.central.count(CentralDemoNote) == 3
    status = env.status()
    assert status.state == "synced"
    assert status.central_acked_through == 6
    assert status.last_success_at == START


def test_nothing_is_marked_synced_while_the_central_is_unreachable(env: Env) -> None:
    env.notes(2)
    env.link.online = False
    result = env.sender().sync_once()
    assert result.status is RunStatus.OFFLINE
    assert result.pending == 4
    assert result.error_code == "sync.offline"
    assert {n.sync_status for n in list_demo_notes(env.site.factory)} == {"pending"}
    status = env.status()
    assert status.state == "offline"
    assert status.offline_since == START
    assert status.consecutive_failures == 1
    with env.site.factory() as session:
        attempts = set(session.scalars(select(OutboxEvent.attempts)))
    assert attempts == {1}


def test_retries_wait_longer_and_longer_up_to_a_ceiling(env: Env) -> None:
    sender = env.sender(backoff_base_ms=2_000, backoff_max_ms=60_000)
    env.notes(1)
    env.link.online = False
    delays = []
    for _ in range(8):
        sender.sync_once(force=True)
        status = env.status()
        assert status.next_attempt_at is not None
        delays.append((status.next_attempt_at - env.site_clock.now()).total_seconds())
    assert 1.6 <= delays[0] <= 2.4  # 2 s ± 20 %
    assert all(a < b for a, b in itertools.pairwise(delays[:6]))  # 2, 4, 8, 16... s
    assert all(48 <= d <= 72 for d in delays[5:])  # plafond 60 s ± 20 %


def test_a_new_attempt_waits_for_the_backoff_unless_forced(env: Env) -> None:
    sender = env.sender()
    env.notes(1)
    env.link.online = False
    sender.sync_once()
    env.link.online = True
    assert sender.sync_once().status is RunStatus.WAITING
    assert env.link.pushes == []
    env.site_clock.advance(timedelta(seconds=3))
    assert sender.sync_once().status is RunStatus.SYNCED


def test_coming_back_online_clears_the_offline_state(env: Env) -> None:
    sender = env.sender()
    env.notes(1)
    env.link.online = False
    sender.sync_once()
    env.site_clock.advance(timedelta(hours=5))
    env.link.online = True
    assert sender.sync_once().status is RunStatus.SYNCED
    status = env.status()
    assert status.offline_since is None
    assert status.consecutive_failures == 0
    assert status.last_error_code is None


def test_a_lost_response_is_resent_without_double_effect(env: Env) -> None:
    sender = env.sender()
    env.notes(2)
    env.link.lose_responses = 1  # le central enregistre, mais la réponse se perd
    assert sender.sync_once().status is RunStatus.OFFLINE
    assert env.central.count(CentralDemoNote) == 2  # déjà enregistré au central...
    assert {n.sync_status for n in list_demo_notes(env.site.factory)} == {
        "pending"
    }  # ... pas affiché
    env.site_clock.advance(timedelta(seconds=5))
    assert sender.sync_once().status is RunStatus.SYNCED
    assert env.central.count(CentralDemoNote) == 2
    assert env.central.count(InboxEvent) == 4
    assert {n.sync_status for n in list_demo_notes(env.site.factory)} == {"synced"}


def test_batches_never_split_a_transaction(env: Env) -> None:
    env.notes(3)
    result = env.sender(batch_size=1).sync_once()
    assert result.status is RunStatus.SYNCED
    assert env.link.pushes == [[1, 2], [3, 4], [5, 6]]  # chaque note voyage avec son audit


def test_a_rejected_event_blocks_and_is_visible(tmp_path: Path) -> None:
    handlers = {"AuditEntryRecorded": CENTRAL_HANDLERS["AuditEntryRecorded"]}
    for env in _make_env(tmp_path, handlers=handlers):  # central qui ignore DemoNoteCreated
        env.notes(2)
        result = env.sender().sync_once()
        assert result.status is RunStatus.REJECTED
        assert result.error_code == "event.unknown_type"
        status = env.status()
        assert status.state == "error"
        assert status.rejected_count == 1
        assert status.pending_count == 4
        # La note du 1er événement est en erreur ; l'autre attend derrière elle.
        assert sorted(n.sync_status for n in list_demo_notes(env.site.factory)) == [
            "error",
            "pending",
        ]
        with env.site.factory() as session:
            row = session.scalars(select(OutboxEvent).where(OutboxEvent.site_seq == 1)).one()
        assert row.status == "rejected"
        assert row.last_error_code == "event.unknown_type"


def test_a_refused_token_is_reported_as_an_error_not_as_offline(env: Env) -> None:
    gateway = HttpCentralGateway(env.client, "nks_jeton_invalide")
    sender = SyncSender(env.site.factory, gateway, env.site_clock)
    env.notes(1)
    result = sender.sync_once()
    assert result.status is RunStatus.REFUSED
    assert result.error_code == "auth.invalid_site_token"
    status = env.status()
    assert status.state == "error"
    assert status.offline_since is None


def test_events_lost_by_the_central_are_sent_again(env: Env, tmp_path: Path) -> None:
    """Le central est restauré depuis une sauvegarde ancienne : le site renvoie ce qui manque."""
    sender = env.sender()
    env.notes(2)
    assert sender.sync_once().status is RunStatus.SYNCED
    # Nouveau central vide (même jeton) : il a « oublié » les 4 premiers événements.
    fresh = open_central_db(sqlite_url(tmp_path / "central-restored.db"), env.central_clock)
    with TestClient(create_central_app(fresh.factory, clock=env.central_clock)) as client:
        gateway = HttpCentralGateway(client, fresh.tokens["S01"])
        restored = SyncSender(env.site.factory, gateway, env.site_clock)
        assert restored.sync_once().status is RunStatus.SYNCED  # battement de cœur : renvoi
        assert fresh.count(InboxEvent) == 4
        env.notes(1)
        assert restored.sync_once().status is RunStatus.SYNCED
        assert fresh.count(CentralDemoNote) == 3
    fresh.close()


def test_a_gap_reported_by_the_central_triggers_a_resend(env: Env, tmp_path: Path) -> None:
    sender = env.sender()
    env.notes(1)
    sender.sync_once()
    fresh = open_central_db(sqlite_url(tmp_path / "central-restored.db"), env.central_clock)
    with TestClient(create_central_app(fresh.factory, clock=env.central_clock)) as client:
        restored = SyncSender(
            env.site.factory, HttpCentralGateway(client, fresh.tokens["S01"]), env.site_clock
        )
        env.notes(1)  # événements 3 et 4 : le central répond « il me manque 1 et 2 »
        assert restored.sync_once().status is RunStatus.SYNCED
        assert fresh.count(InboxEvent) == 4


def test_clock_offset_with_the_central_is_measured(env: Env) -> None:
    env.site_clock.advance(timedelta(days=2))  # PC du site en avance de 2 jours
    env.sender().sync_once()
    status = env.status()
    assert status.clock_offset_seconds == -2 * 24 * 3600
    assert status.clock_alert


def test_a_clock_moved_back_offline_raises_an_alert(env: Env) -> None:
    env.sender().sync_once()
    assert not env.status().clock_alert
    env.link.online = False
    env.site_clock.advance(timedelta(hours=-1))  # quelqu'un recule l'heure du PC
    assert env.status().clock_alert


def test_a_corrupted_outbox_blocks_sending(env: Env) -> None:
    env.notes(1)
    with env.site.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER trg_sync_outbox_immutable"))
        conn.execute(text('UPDATE sync_outbox SET payload = \'{"text":"x"}\' WHERE site_seq = 1'))
    result = env.sender().sync_once()
    assert result.status is RunStatus.ERROR
    assert result.error_code == "sync.outbox_corrupted"
    assert env.link.pushes == []


def test_two_passes_at_the_same_time_do_not_overlap(env: Env) -> None:
    entered, release = threading.Event(), threading.Event()

    class SlowGateway:
        """Central très lent : la première requête reste bloquée jusqu'au signal."""

        def push(self, request: PushRequest) -> PushResponse:
            raise CentralUnavailableError(detail="inutilisé")

        def fetch_state(self) -> SiteSyncState:
            entered.set()
            release.wait(5)
            raise CentralUnavailableError(detail="délai dépassé")

    sender = SyncSender(env.site.factory, SlowGateway(), env.site_clock)
    thread = threading.Thread(target=sender.sync_once)
    thread.start()
    assert entered.wait(5)
    assert sender.sync_once().status is RunStatus.BUSY
    release.set()
    thread.join(5)


def test_the_background_worker_synchronizes_on_its_own(env: Env) -> None:
    worker = SyncWorker(env.sender(), interval_seconds=0.05)
    worker.start()
    try:
        env.notes(2)
        worker.trigger()
        deadline = threading.Event()
        for _ in range(100):
            if env.central.count(CentralDemoNote) == 2:
                break
            deadline.wait(0.05)
        assert env.central.count(CentralDemoNote) == 2
    finally:
        worker.stop()
    assert not worker.running
