"""Messages échangés entre un nœud de site et le central.

Le site envoie un **lot** d'événements (``PushRequest``), dans l'ordre de ``site_seq``.
Le central répond par un **accusé de réception** (``PushResponse``) :

- ``acked_through`` : tous les événements jusqu'à ce numéro sont enregistrés au central.
  Le site peut les marquer « synchronisés ». C'est le seul signal qui autorise
  l'affichage « consolidé ».
- ``status`` : ``ok`` (tout est passé), ``gap`` (il manque des événements avant ce lot :
  renvoyer à partir de ``expected_next``), ``rejected`` (un événement est refusé, l'envoi
  est bloqué à cet endroit), ``conflict`` (numéro déjà utilisé par un autre événement, ou
  même événement au contenu différent : anomalie grave à faire examiner).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from nkap.events.envelope import MAX_TX_SIZE, EventEnvelope

PROTOCOL_VERSION = 1
MAX_BATCH_EVENTS = MAX_TX_SIZE
"""Un lot peut toujours contenir une transaction entière (jamais coupée en deux)."""

PUSH_PATH = "/api/v1/sync/events"
STATE_PATH = "/api/v1/sync/state"


class PushStatus(StrEnum):
    OK = "ok"
    GAP = "gap"
    REJECTED = "rejected"
    CONFLICT = "conflict"


class PushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Annotated[StrictInt, Field(ge=1)]
    site_id: UUID
    events: Annotated[list[EventEnvelope], Field(min_length=1, max_length=MAX_BATCH_EVENTS)]


class RejectedEvent(BaseModel):
    """Événement sur lequel l'envoi est bloqué, avec la raison (code + message)."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    site_seq: int
    code: str
    message: str


class PushResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PushStatus
    acked_through: int
    expected_next: int
    server_time: AwareDatetime
    rejected: RejectedEvent | None = None


class SiteSyncState(BaseModel):
    """Ce que le central sait d'un site (pour le diagnostic et la reconstruction)."""

    model_config = ConfigDict(extra="forbid")

    site_id: UUID
    acked_through: int
    audit_last_seq: int
    last_received_at: AwareDatetime | None
    server_time: AwareDatetime


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Format commun des erreurs de l'API (code stable + message en français)."""

    error: ErrorBody
