"""API du nœud de site (appelée par les postes PySide6 à partir de l'étape 2)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nkap.central.api import create_central_app
from nkap.core.clock import FakeClock
from nkap.site_node.api import create_site_app
from nkap.site_node.gateway import HttpCentralGateway
from nkap.site_node.sync_sender import SyncSender
from support.central import open_central_db
from support.db import sqlite_url
from support.site import SiteDb, open_site_db


@pytest.fixture
def site(tmp_path: Path, clock: FakeClock) -> Iterator[SiteDb]:
    db = open_site_db(sqlite_url(tmp_path / "site.db"), clock)
    yield db
    db.close()


@pytest.fixture
def offline_client(site: SiteDb, clock: FakeClock) -> Iterator[TestClient]:
    """Site sans synchronisation configurée."""
    app = create_site_app(session_factory=site.factory, uow=site.uow, clock=clock)
    with TestClient(app) as client:
        yield client


def test_health_reports_the_site(offline_client: TestClient) -> None:
    body = offline_client.get("/api/v1/health").json()
    assert body == {"status": "ok", "role": "site", "site_code": "S01", "version": "0.1.0"}


def test_notes_are_created_and_listed_with_their_sync_status(offline_client: TestClient) -> None:
    created = offline_client.post(
        "/api/v1/demo-notes", json={"text": "Livraison", "business_date": "2026-10-17"}
    )
    assert created.status_code == 201
    note = created.json()
    assert note["sync_status"] == "pending"
    assert note["business_date"] == "2026-10-17"
    assert offline_client.get("/api/v1/demo-notes").json() == [note]
    status = offline_client.get("/api/v1/sync/status").json()
    assert status["state"] == "pending"
    assert status["pending_count"] == 2


@pytest.mark.parametrize("body", [{"text": "   "}, {"text": "x" * 501}, {"txt": "a"}, {}])
def test_invalid_notes_are_refused(offline_client: TestClient, body: dict[str, str]) -> None:
    response = offline_client.post("/api/v1/demo-notes", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request.invalid"


def test_sync_run_without_configuration_is_refused(offline_client: TestClient) -> None:
    response = offline_client.post("/api/v1/sync/run")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "sync.disabled"


def test_audit_verification_endpoint(offline_client: TestClient) -> None:
    offline_client.post("/api/v1/demo-notes", json={"text": "a"})
    assert offline_client.get("/api/v1/audit/verify").json() == {
        "ok": True,
        "checked": 1,
        "first_broken_seq": None,
        "reason": None,
    }


def test_sync_run_sends_to_the_central(site: SiteDb, clock: FakeClock, tmp_path: Path) -> None:
    central = open_central_db(sqlite_url(tmp_path / "central.db"), clock)
    with TestClient(create_central_app(central.factory, clock=clock)) as central_client:
        sender = SyncSender(
            site.factory, HttpCentralGateway(central_client, central.tokens["S01"]), clock
        )
        app = create_site_app(
            session_factory=site.factory, uow=site.uow, clock=clock, sender=sender
        )
        with TestClient(app) as client:
            client.post("/api/v1/demo-notes", json={"text": "a"})
            result = client.post("/api/v1/sync/run").json()
            assert result["status"] == "synced"
            assert result["acked"] == 2
            notes = client.get("/api/v1/demo-notes").json()
            assert notes[0]["sync_status"] == "synced"
    central.close()


def test_health_before_initialization(tmp_path: Path, clock: FakeClock) -> None:
    blank = open_site_db(sqlite_url(tmp_path / "blank.db"), clock, identity=None)
    app = create_site_app(session_factory=blank.factory, uow=blank.uow, clock=clock)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json()["site_code"] is None
        response = client.post("/api/v1/demo-notes", json={"text": "a"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "site.not_initialized"
    blank.close()
