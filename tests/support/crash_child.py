"""Programme lancé dans un processus séparé, que les tests tuent brutalement (T17).

Usage : ``python -m support.crash_child <scénario> <arguments...>``

Scénarios :

- ``write-forever SITE_URL`` : crée des notes sans arrêt (le test tue le processus au hasard).
- ``die-in-transaction SITE_URL`` : meurt au milieu d'une transaction, données déjà écrites
  dans la base mais pas encore validées.
- ``die-before-ack SITE_URL CENTRAL_URL TOKEN`` : envoie au central, qui enregistre, puis
  meurt avant d'avoir noté l'accusé de réception.
- ``sync-forever SITE_URL CENTRAL_URL TOKEN`` : crée des notes et synchronise sans arrêt.

Le processus écrit « ready » dès qu'il a commencé à travailler.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from nkap.central.api import create_central_app
from nkap.core.clock import SystemClock
from nkap.core.db import create_db_engine, make_session_factory
from nkap.core.orm import Actor
from nkap.site_node.demo_notes import create_demo_note
from nkap.site_node.gateway import HttpCentralGateway
from nkap.site_node.sync_sender import SyncSender
from nkap.site_node.unit_of_work import SiteTransaction, SiteUnitOfWork

KILLED = 137


def _ready() -> None:
    print("ready", flush=True)


def _site(url: str) -> SiteUnitOfWork:
    return SiteUnitOfWork(make_session_factory(create_db_engine(url)), SystemClock())


def _sender(uow: SiteUnitOfWork, central_url: str, token: str) -> SyncSender:
    central_factory = make_session_factory(create_db_engine(central_url))
    client = TestClient(create_central_app(central_factory, clock=SystemClock()))
    return SyncSender(uow.session_factory, HttpCentralGateway(client, token), uow.clock)


def write_forever(site_url: str) -> None:
    uow = _site(site_url)
    i = 0
    while True:
        create_demo_note(uow, f"enfant {i}", actor=Actor.system())
        if i == 0:
            _ready()
        i += 1


def die_in_transaction(site_url: str) -> None:
    uow = _site(site_url)
    original = SiteTransaction.write_outbox

    def write_then_die(self: SiteTransaction) -> Any:
        result = original(self)
        self.session.flush()  # tout est écrit dans la base... sauf la validation finale
        _ready()
        os._exit(KILLED)
        return result  # pragma: no cover

    SiteTransaction.write_outbox = write_then_die  # type: ignore[method-assign]
    create_demo_note(uow, "jamais validée", actor=Actor.system())


def die_before_ack(site_url: str, central_url: str, token: str) -> None:
    uow = _site(site_url)
    sender = _sender(uow, central_url, token)

    def die(*_args: object, **_kwargs: object) -> Any:
        _ready()
        os._exit(KILLED)

    sender._apply_response = die  # type: ignore[method-assign]
    sender.sync_once(force=True)


def sync_forever(site_url: str, central_url: str, token: str) -> None:
    uow = _site(site_url)
    sender = _sender(uow, central_url, token)
    i = 0
    while True:
        create_demo_note(uow, f"enfant {i}", actor=Actor.system())
        sender.sync_once(force=True)
        if i == 0:
            _ready()
        i += 1


SCENARIOS: dict[str, Callable[..., None]] = {
    "write-forever": write_forever,
    "die-in-transaction": die_in_transaction,
    "die-before-ack": die_before_ack,
    "sync-forever": sync_forever,
}


if __name__ == "__main__":
    SCENARIOS[sys.argv[1]](*sys.argv[2:])
