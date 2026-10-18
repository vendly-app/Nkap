"""Conversion entre une ligne de la file d'envoi (``sync_outbox``) et une enveloppe."""

from __future__ import annotations

import json

from nkap.core.canonical import canonical_json
from nkap.core.errors import NkapError
from nkap.events.envelope import EventEnvelope
from nkap.site_node.models import OUTBOX_PENDING, OutboxEvent


class OutboxCorruptedError(NkapError):
    """Une ligne de la file d'envoi ne correspond plus à son empreinte d'origine."""

    default_code = "sync.outbox_corrupted"


def outbox_row_from_envelope(envelope: EventEnvelope) -> OutboxEvent:
    return OutboxEvent(
        event_id=envelope.event_id,
        site_seq=envelope.site_seq,
        tx_id=envelope.tx_id,
        tx_size=envelope.tx_size,
        event_type=envelope.event_type,
        payload_version=envelope.payload_version,
        company_id=envelope.company_id,
        site_id=envelope.site_id,
        entity_type=envelope.entity_type,
        entity_id=envelope.entity_id,
        entity_version=envelope.entity_version,
        occurred_at=envelope.occurred_at,
        business_date=envelope.business_date,
        created_by=envelope.created_by,
        payload=canonical_json(envelope.payload),
        fingerprint=envelope.fingerprint(),
        status=OUTBOX_PENDING,
        attempts=0,
    )


def envelope_from_outbox_row(row: OutboxEvent) -> EventEnvelope:
    """Reconstruit l'enveloppe et vérifie qu'elle n'a pas été altérée depuis sa création."""
    envelope = EventEnvelope(
        event_id=row.event_id,
        event_type=row.event_type,
        payload_version=row.payload_version,
        company_id=row.company_id,
        site_id=row.site_id,
        site_seq=row.site_seq,
        tx_id=row.tx_id,
        tx_size=row.tx_size,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        entity_version=row.entity_version,
        occurred_at=row.occurred_at,
        business_date=row.business_date,
        created_by=row.created_by,
        payload=json.loads(row.payload),
    )
    if envelope.fingerprint() != row.fingerprint:
        raise OutboxCorruptedError(site_seq=row.site_seq)
    return envelope
