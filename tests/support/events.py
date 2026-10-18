"""Fabrication d'événements pour les tests."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from nkap.events.envelope import EventEnvelope

COMPANY_ID = uuid.UUID("01900000-0000-7000-8000-00000000c001")
SITE_A = uuid.UUID("01900000-0000-7000-8000-00000000a001")
SITE_B = uuid.UUID("01900000-0000-7000-8000-00000000b001")


def envelope_data(**overrides: Any) -> dict[str, Any]:
    """Données d'une enveloppe ``DemoNoteCreated`` valide, modifiables champ par champ."""
    data: dict[str, Any] = {
        "event_id": uuid.uuid4(),
        "event_type": "DemoNoteCreated",
        "payload_version": 1,
        "company_id": COMPANY_ID,
        "site_id": SITE_A,
        "site_seq": 1,
        "tx_id": uuid.uuid4(),
        "tx_size": 1,
        "entity_type": "demo_note",
        "entity_id": uuid.uuid4(),
        "entity_version": 1,
        "occurred_at": datetime(2026, 10, 18, 8, 0, tzinfo=UTC),
        "business_date": date(2026, 10, 18),
        "created_by": None,
        "payload": {"text": "Note de test"},
    }
    data.update(overrides)
    return data


def make_envelope(**overrides: Any) -> EventEnvelope:
    return EventEnvelope.model_validate(envelope_data(**overrides))
