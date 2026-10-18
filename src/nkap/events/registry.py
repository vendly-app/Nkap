"""Registre des types d'événements et de leurs versions.

Chaque type d'événement (ex. ``DemoNoteCreated``) a un ou plusieurs formats de contenu
numérotés (``payload_version``). Le central garde les anciennes versions enregistrées :
un site resté en version N-1 peut donc continuer à se synchroniser après la mise à jour
du central. Règle de déploiement : **le central est mis à jour avant les sites**.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from nkap.core.errors import NkapError
from nkap.events.envelope import EventEnvelope


class UnknownEventError(NkapError):
    """Type d'événement (ou version) inconnu."""

    default_code = "event.unknown_type"


class InvalidEventError(NkapError):
    """Événement connu mais au contenu invalide."""

    default_code = "event.invalid_payload"


@dataclass(frozen=True, slots=True)
class EventDefinition:
    """Description d'une version d'un type d'événement."""

    event_type: str
    payload_version: int
    entity_type: str
    payload_model: type[BaseModel]


class EventRegistry:
    """Catalogue des événements reconnus."""

    def __init__(self) -> None:
        self._definitions: dict[tuple[str, int], EventDefinition] = {}

    def register(self, definition: EventDefinition) -> None:
        key = (definition.event_type, definition.payload_version)
        if key in self._definitions:
            raise ValueError(f"Événement déjà enregistré : {key}.")
        self._definitions[key] = definition

    def get(self, event_type: str, payload_version: int) -> EventDefinition:
        definition = self._definitions.get((event_type, payload_version))
        if definition is None:
            raise UnknownEventError(event_type=event_type, payload_version=payload_version)
        return definition

    def latest_version(self, event_type: str) -> int:
        versions = [v for (name, v) in self._definitions if name == event_type]
        if not versions:
            raise UnknownEventError(event_type=event_type, payload_version="?")
        return max(versions)

    def parse_payload(self, envelope: EventEnvelope) -> BaseModel:
        """Vérifie un événement reçu et renvoie son contenu sous forme typée."""
        definition = self.get(envelope.event_type, envelope.payload_version)
        if envelope.entity_type != definition.entity_type:
            raise InvalidEventError(
                "event.entity_mismatch",
                event_type=envelope.event_type,
                expected=definition.entity_type,
                actual=envelope.entity_type,
            )
        try:
            return definition.payload_model.model_validate(envelope.payload)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
            )
            raise InvalidEventError(event_type=envelope.event_type, details=details) from exc
