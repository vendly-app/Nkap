"""API HTTP du central (FastAPI).

- ``GET  /api/v1/health`` : le central répond-il ?
- ``POST /api/v1/sync/events`` : un site envoie un lot d'événements, reçoit l'accusé.
- ``GET  /api/v1/sync/state`` : ce que le central sait du site qui appelle.
"""

# Pas de « from __future__ import annotations » ici : FastAPI doit pouvoir lire les
# annotations des fonctions d'API, y compris les dépendances définies localement.
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from nkap import __version__
from nkap.central.auth import AuthenticatedSite, authenticate
from nkap.central.handlers import CENTRAL_HANDLERS, Handler
from nkap.central.ingest import SyncIngestor
from nkap.central.models import SyncSiteState
from nkap.core.clock import Clock
from nkap.core.http import install_error_handlers
from nkap.events.catalog import build_registry
from nkap.events.registry import EventRegistry
from nkap.sync.protocol import (
    PUSH_PATH,
    STATE_PATH,
    PushRequest,
    PushResponse,
    SiteSyncState,
)

_bearer = HTTPBearer(auto_error=False)


def create_central_app(
    session_factory: sessionmaker[Session],
    *,
    clock: Clock,
    registry: EventRegistry | None = None,
    handlers: dict[str, Handler] | None = None,
) -> FastAPI:
    registry = registry or build_registry()
    ingestor = SyncIngestor(session_factory, clock, registry, handlers or CENTRAL_HANDLERS)
    app = FastAPI(title="Nkap — central", version=__version__)
    install_error_handlers(app)

    def require_site(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> AuthenticatedSite:
        with session_factory() as session:
            return authenticate(session, credentials.credentials if credentials else None)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "role": "central", "version": __version__}

    @app.post(PUSH_PATH)
    def push_events(
        request: PushRequest,
        site: Annotated[AuthenticatedSite, Depends(require_site)],
    ) -> PushResponse:
        return ingestor.ingest(site, request)

    @app.get(STATE_PATH)
    def site_state(site: Annotated[AuthenticatedSite, Depends(require_site)]) -> SiteSyncState:
        with session_factory() as session:
            state = session.get(SyncSiteState, site.site_id)
            if state is None:  # pragma: no cover - créé à l'enregistrement du site
                raise RuntimeError("État de synchronisation absent.")
            return SiteSyncState(
                site_id=site.site_id,
                acked_through=state.last_seq,
                audit_last_seq=state.audit_last_seq,
                last_received_at=state.last_received_at,
                server_time=clock.now(),
            )

    return app
