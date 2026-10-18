"""Liaison réseau simulée entre un site et le central.

Permet de couper Internet, ou de « perdre » la réponse du central après qu'il a traité
la requête (le cas le plus piégeux : le central a tout enregistré, le site ne le sait pas).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nkap.site_node.gateway import CentralGateway, CentralUnavailableError
from nkap.sync.protocol import PushRequest, PushResponse, SiteSyncState


@dataclass
class NetworkLink:
    online: bool = True
    lose_responses: int = 0
    """Nombre de prochaines réponses perdues (requête traitée par le central, réponse perdue)."""
    pushes: list[list[int]] = field(default_factory=list)
    """Numéros ``site_seq`` de chaque lot qui a atteint le central."""
    heartbeats: int = 0

    def _check_online(self) -> None:
        if not self.online:
            raise CentralUnavailableError(detail="ConnectError (coupure simulée)")

    def _maybe_lose(self) -> None:
        if self.lose_responses > 0:
            self.lose_responses -= 1
            raise CentralUnavailableError(detail="ReadTimeout (réponse perdue, simulée)")


class LinkedGateway:
    """Passerelle qui fait passer chaque appel par une liaison simulée."""

    def __init__(self, inner: CentralGateway, link: NetworkLink) -> None:
        self.inner = inner
        self.link = link

    def push(self, request: PushRequest) -> PushResponse:
        self.link._check_online()
        self.link.pushes.append([e.site_seq for e in request.events])
        response = self.inner.push(request)
        self.link._maybe_lose()
        return response

    def fetch_state(self) -> SiteSyncState:
        self.link._check_online()
        self.link.heartbeats += 1
        state = self.inner.fetch_state()
        self.link._maybe_lose()
        return state
