"""API HTTP du nœud de site (FastAPI), appelée par les postes du site.

Étape 1 : pas encore d'utilisateurs ni de droits (étape 2). Le service n'écoute donc que
sur la machine elle-même (``127.0.0.1``) par défaut.

- ``GET  /api/v1/health`` : le service répond-il, pour quel site ?
- ``POST /api/v1/demo-notes`` / ``GET /api/v1/demo-notes`` : notes factices.
- ``GET  /api/v1/sync/status`` : état de la synchronisation (bandeau « hors ligne »).
- ``POST /api/v1/sync/run`` : lancer une synchronisation maintenant.
- ``GET  /api/v1/audit/verify`` : vérifier l'intégrité du journal d'audit.
"""

# Pas de « from __future__ import annotations » : FastAPI lit les annotations à l'exécution.
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session, sessionmaker

from nkap import __version__
from nkap.core.clock import Clock
from nkap.core.errors import NkapError
from nkap.core.http import install_error_handlers
from nkap.core.orm import Actor
from nkap.site_node.audit_log import verify_audit_log
from nkap.site_node.demo_notes import create_demo_note, list_demo_notes
from nkap.site_node.identity import NodeNotInitializedError, load_identity
from nkap.site_node.models import DemoNote
from nkap.site_node.sync_sender import RunStatus, SyncSender
from nkap.site_node.sync_status import SyncStatusView, read_sync_status
from nkap.site_node.unit_of_work import SiteUnitOfWork
from nkap.site_node.worker import SyncWorker


class SyncDisabledError(NkapError):
    default_code = "sync.disabled"
    http_status = 409


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    business_date: date | None = None


class NoteOut(BaseModel):
    id: UUID
    text: str
    business_date: date
    created_at: datetime
    sync_status: str

    @classmethod
    def of(cls, note: DemoNote) -> "NoteOut":
        return cls(
            id=note.id,
            text=note.text,
            business_date=note.business_date,
            created_at=note.created_at,
            sync_status=note.sync_status,
        )


class SyncRunOut(BaseModel):
    status: RunStatus
    sent: int
    acked: int
    pending: int
    error_code: str | None
    error_message: str | None


class AuditCheckOut(BaseModel):
    ok: bool
    checked: int
    first_broken_seq: int | None
    reason: str | None


def create_site_app(
    *,
    session_factory: sessionmaker[Session],
    uow: SiteUnitOfWork,
    clock: Clock,
    sender: SyncSender | None = None,
    worker: SyncWorker | None = None,
    drift_tolerance: timedelta = timedelta(minutes=10),
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if worker is not None:
            worker.start()
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()

    app = FastAPI(title="Nkap — nœud de site", version=__version__, lifespan=lifespan)
    install_error_handlers(app)

    @app.get("/api/v1/health")
    def health() -> dict[str, str | None]:
        try:
            with session_factory() as session:
                site_code: str | None = load_identity(session).site_code
        except NodeNotInitializedError:
            site_code = None
        return {"status": "ok", "role": "site", "site_code": site_code, "version": __version__}

    @app.post("/api/v1/demo-notes", status_code=201)
    def add_note(note: NoteIn) -> NoteOut:
        created = create_demo_note(
            uow, note.text, actor=Actor.system(), business_date=note.business_date
        )
        if worker is not None:
            worker.trigger()  # envoi au central sans attendre, si la liaison le permet
        return NoteOut.of(created)

    @app.get("/api/v1/demo-notes")
    def notes() -> list[NoteOut]:
        return [NoteOut.of(n) for n in list_demo_notes(session_factory)]

    @app.get("/api/v1/sync/status")
    def sync_status() -> SyncStatusView:
        with session_factory() as session:
            return read_sync_status(session, clock, drift_tolerance)

    @app.post("/api/v1/sync/run")
    def sync_run() -> SyncRunOut:
        if sender is None:
            raise SyncDisabledError()
        result = sender.sync_once(force=True)
        return SyncRunOut(
            status=result.status,
            sent=result.sent,
            acked=result.acked,
            pending=result.pending,
            error_code=result.error_code,
            error_message=result.error_message,
        )

    @app.get("/api/v1/audit/verify")
    def audit_verify() -> AuditCheckOut:
        with session_factory() as session:
            check = verify_audit_log(session)
        return AuditCheckOut(
            ok=check.ok,
            checked=check.checked,
            first_broken_seq=check.first_broken_seq,
            reason=check.reason,
        )

    return app
