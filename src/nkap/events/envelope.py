"""Enveloppe commune à tous les événements de synchronisation (décision 008)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
)

from nkap.core.canonical import canonical_json, sha256_hex
from nkap.i18n import translate

MAX_TX_SIZE = 1000
"""Nombre maximal d'événements produits par une seule transaction locale."""

PositiveInt = Annotated[StrictInt, Field(ge=1)]
EventTypeName = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Za-z0-9]{2,63}$")]
EntityTypeName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,63}$")]


def reject_floats(value: object) -> None:
    """Parcourt une structure JSON et refuse tout nombre à virgule flottante."""
    if isinstance(value, float):
        raise ValueError(translate("event.float_forbidden"))
    if isinstance(value, dict):
        for item in value.values():
            reject_floats(item)
    elif isinstance(value, list | tuple):
        for item in value:
            reject_floats(item)


class EventEnvelope(BaseModel):
    """Un événement tel qu'il circule entre un site et le central.

    Champs principaux :

    - ``event_id`` : identifiant unique (UUIDv7) ; sert à ignorer les doublons.
    - ``site_id`` / ``site_seq`` : site d'origine et numéro d'ordre sur ce site
      (1, 2, 3... sans trou). C'est **le seul ordre** qui fait foi.
    - ``tx_id`` / ``tx_size`` : les événements écrits dans une même transaction locale
      partagent ``tx_id`` ; le central les applique tous ensemble ou aucun.
    - ``entity_type`` / ``entity_id`` / ``entity_version`` : l'objet concerné.
    - ``occurred_at`` : heure locale du site au moment de l'opération (indicative).
    - ``business_date`` : date métier ou comptable de l'opération.
    - ``payload`` : contenu propre au type d'événement (``payload_version``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    event_type: EventTypeName
    payload_version: PositiveInt
    company_id: UUID
    site_id: UUID
    site_seq: PositiveInt
    tx_id: UUID
    tx_size: Annotated[StrictInt, Field(ge=1, le=MAX_TX_SIZE)]
    entity_type: EntityTypeName
    entity_id: UUID
    entity_version: PositiveInt
    occurred_at: AwareDatetime
    business_date: date | None = None
    created_by: UUID | None = None
    payload: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def _normalize_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("payload")
    @classmethod
    def _payload_without_floats(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_floats(value)
        return value

    def fingerprint(self) -> str:
        """Empreinte SHA-256 du contenu complet de l'événement.

        Si le central reçoit deux fois le même ``event_id`` avec des empreintes
        différentes, ce n'est pas un doublon mais une anomalie grave.
        """
        return sha256_hex(canonical_json(self.model_dump()))
