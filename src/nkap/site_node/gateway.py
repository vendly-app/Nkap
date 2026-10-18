"""Passerelle du site vers le central (appel HTTP).

Deux familles d'échecs, traitées différemment par l'envoi :

- ``CentralUnavailableError`` : le central est **injoignable** (pas d'Internet, délai
  dépassé, serveur en panne). Situation normale hors ligne : on réessaiera plus tard.
- ``CentralRefusedError`` : le central a **répondu mais refusé** la requête (jeton invalide,
  site non autorisé, requête mal formée). Il faut l'intervention d'un administrateur.
"""

from __future__ import annotations

from typing import Protocol

import httpx2
from pydantic import BaseModel, ValidationError

from nkap.core.errors import NkapError
from nkap.sync.protocol import PUSH_PATH, STATE_PATH, PushRequest, PushResponse, SiteSyncState

DEFAULT_TIMEOUT = httpx2.Timeout(30.0, connect=10.0)


class CentralUnavailableError(NkapError):
    default_code = "sync.offline"


class CentralRefusedError(NkapError):
    default_code = "sync.refused"

    def __init__(self, *, status: int, remote_code: str, reason: str) -> None:
        super().__init__(status=status, reason=reason)
        self.remote_code = remote_code
        """Code d'erreur renvoyé par le central (ex. ``auth.invalid_site_token``)."""


class CentralGateway(Protocol):
    def push(self, request: PushRequest) -> PushResponse:
        """Envoie un lot d'événements et renvoie l'accusé de réception."""
        ...

    def fetch_state(self) -> SiteSyncState:
        """Demande au central où il en est pour ce site (battement de cœur)."""
        ...


def make_http_client(central_url: str, timeout: httpx2.Timeout = DEFAULT_TIMEOUT) -> httpx2.Client:
    """Client HTTP vers le central (certificats vérifiés avec le magasin du système)."""
    return httpx2.Client(base_url=central_url, timeout=timeout)


class HttpCentralGateway:
    """Envoie les lots au central par HTTP(S)."""

    def __init__(self, client: httpx2.Client, token: str) -> None:
        self._client = client
        self._token = token

    def push(self, request: PushRequest) -> PushResponse:
        response = self._call("POST", PUSH_PATH, content=request.model_dump_json())
        return _parse(PushResponse, response)

    def fetch_state(self) -> SiteSyncState:
        return _parse(SiteSyncState, self._call("GET", STATE_PATH))

    def _call(self, method: str, path: str, content: str | None = None) -> httpx2.Response:
        headers = {"Authorization": f"Bearer {self._token}"}
        if content is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = self._client.request(method, path, content=content, headers=headers)
        except httpx2.TransportError as exc:  # réseau coupé, délai dépassé, DNS...
            raise CentralUnavailableError(detail=type(exc).__name__) from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise CentralUnavailableError(detail=f"HTTP {response.status_code}")
        if response.status_code != 200:
            remote_code, reason = _error_of(response)
            raise CentralRefusedError(
                status=response.status_code, remote_code=remote_code, reason=reason
            )
        return response


def _parse[ModelT: BaseModel](model: type[ModelT], response: httpx2.Response) -> ModelT:
    try:
        return model.model_validate_json(response.content)
    except ValidationError as exc:
        raise CentralRefusedError(
            status=response.status_code, remote_code="sync.bad_response", reason="réponse illisible"
        ) from exc


def _error_of(response: httpx2.Response) -> tuple[str, str]:
    try:
        error = response.json()["error"]
        return str(error["code"]), str(error["message"])
    except (ValueError, KeyError, TypeError):
        return "sync.refused", f"HTTP {response.status_code}"
