"""Catalogue des événements de l'étape 1.

- ``DemoNoteCreated`` : événement **factice** (une simple note texte) qui sert à prouver
  que la chaîne complète site → central fonctionne avant d'y brancher le vrai métier.
- ``AuditEntryRecorded`` : réplication d'une ligne du journal d'audit d'un site vers le
  central (décision 007). Le central vérifie la continuité de la chaîne d'empreintes.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

from nkap.events.envelope import EntityTypeName, PositiveInt
from nkap.events.registry import EventDefinition, EventRegistry

DEMO_NOTE = "demo_note"
AUDIT_ENTRY = "audit_entry"

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
AuditAction = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.]{1,63}$")]


class DemoNoteCreatedV1(BaseModel):
    """Contenu de ``DemoNoteCreated`` version 1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AuditEntryRecordedV1(BaseModel):
    """Contenu de ``AuditEntryRecorded`` version 1 (une ligne du journal d'audit)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chain_seq: PositiveInt
    occurred_at: AwareDatetime
    actor_id: UUID | None
    actor_label: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    action: AuditAction
    entity_type: EntityTypeName | None
    entity_id: UUID | None
    details: dict[str, Any]
    prev_hash: Sha256Hex
    hash: Sha256Hex


DEMO_NOTE_CREATED = EventDefinition("DemoNoteCreated", 1, DEMO_NOTE, DemoNoteCreatedV1)
AUDIT_ENTRY_RECORDED = EventDefinition("AuditEntryRecorded", 1, AUDIT_ENTRY, AuditEntryRecordedV1)


def build_registry() -> EventRegistry:
    """Registre contenant tous les événements connus de cette version du logiciel."""
    registry = EventRegistry()
    registry.register(DEMO_NOTE_CREATED)
    registry.register(AUDIT_ENTRY_RECORDED)
    return registry
