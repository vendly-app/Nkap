import pytest

from nkap.events.catalog import (
    DEMO_NOTE_CREATED,
    AuditEntryRecordedV1,
    DemoNoteCreatedV1,
    build_registry,
)
from nkap.events.registry import EventRegistry, InvalidEventError, UnknownEventError
from support.events import make_envelope


def test_known_event_payload_is_parsed_into_its_model() -> None:
    payload = build_registry().parse_payload(make_envelope(payload={"text": "  Bonjour  "}))
    assert isinstance(payload, DemoNoteCreatedV1)
    assert payload.text == "Bonjour"


def test_unknown_event_type_or_version_is_reported_with_a_code() -> None:
    registry = build_registry()
    with pytest.raises(UnknownEventError) as exc_info:
        registry.parse_payload(make_envelope(event_type="StockShipped"))
    assert exc_info.value.code == "event.unknown_type"
    assert "mis à jour" in str(exc_info.value)
    with pytest.raises(UnknownEventError):
        registry.parse_payload(make_envelope(payload_version=2))


def test_entity_type_must_match_the_event_definition() -> None:
    with pytest.raises(InvalidEventError) as exc_info:
        build_registry().parse_payload(make_envelope(entity_type="audit_entry"))
    assert exc_info.value.code == "event.entity_mismatch"


@pytest.mark.parametrize("payload", [{"text": ""}, {"text": "   "}, {"text": "a", "x": 1}, {}])
def test_invalid_payloads_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(InvalidEventError) as exc_info:
        build_registry().parse_payload(make_envelope(payload=payload))
    assert exc_info.value.code == "event.invalid_payload"


def test_registering_the_same_version_twice_is_an_error() -> None:
    registry = EventRegistry()
    registry.register(DEMO_NOTE_CREATED)
    with pytest.raises(ValueError, match="déjà"):
        registry.register(DEMO_NOTE_CREATED)


def test_latest_version() -> None:
    registry = build_registry()
    assert registry.latest_version("DemoNoteCreated") == 1
    with pytest.raises(UnknownEventError):
        registry.latest_version("Inconnu")


def test_audit_entry_payload_requires_valid_hashes() -> None:
    registry = build_registry()
    good = {
        "chain_seq": 1,
        "occurred_at": "2026-10-18T08:00:00Z",
        "actor_id": None,
        "actor_label": "système",
        "action": "demo_note.create",
        "entity_type": "demo_note",
        "entity_id": None,
        "details": {},
        "prev_hash": "0" * 64,
        "hash": "a" * 64,
    }
    env = make_envelope(event_type="AuditEntryRecorded", entity_type="audit_entry", payload=good)
    assert isinstance(registry.parse_payload(env), AuditEntryRecordedV1)
    bad = make_envelope(
        event_type="AuditEntryRecorded",
        entity_type="audit_entry",
        payload={**good, "hash": "pas-une-empreinte"},
    )
    with pytest.raises(InvalidEventError):
        registry.parse_payload(bad)
