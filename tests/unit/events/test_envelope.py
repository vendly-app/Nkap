from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nkap.events.envelope import EventEnvelope
from support.events import envelope_data, make_envelope


def test_envelope_survives_a_json_round_trip_unchanged() -> None:
    original = make_envelope()
    wire = original.model_dump_json()
    received = EventEnvelope.model_validate_json(wire)
    assert received == original
    assert received.fingerprint() == original.fingerprint()


def test_fingerprint_changes_when_any_content_changes() -> None:
    base = envelope_data()
    one = EventEnvelope.model_validate(base)
    other = EventEnvelope.model_validate({**base, "payload": {"text": "Autre texte"}})
    assert one.fingerprint() != other.fingerprint()


def test_occurred_at_is_normalized_to_utc() -> None:
    douala = timezone(timedelta(hours=1))
    env = make_envelope(occurred_at=datetime(2026, 10, 18, 9, 0, tzinfo=douala))
    assert env.occurred_at == datetime(2026, 10, 18, 8, 0, tzinfo=UTC)
    assert env.occurred_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"unexpected": "champ"},  # champ inconnu
        {"occurred_at": datetime(2026, 10, 18, 8, 0)},  # noqa: DTZ001 - sans fuseau
        {"site_seq": 0},
        {"site_seq": "5"},  # pas de conversion implicite des nombres
        {"site_seq": 5.0},
        {"tx_size": 0},
        {"tx_size": 1001},
        {"event_type": "demo_note_created"},  # format du nom de type
        {"entity_type": "DemoNote"},
        {"payload_version": 0},
        {"payload": {"montant": 12.5}},  # float interdit
        {"payload": {"lignes": [{"quantite": 0.5}]}},  # même imbriqué
    ],
)
def test_invalid_envelopes_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_envelope(**overrides)


def test_envelope_is_immutable() -> None:
    env = make_envelope()
    with pytest.raises(ValidationError):
        env.site_seq = 2  # type: ignore[misc]


def test_json_with_float_in_payload_is_rejected() -> None:
    wire = make_envelope().model_dump_json().replace('"Note de test"', "1.5")
    with pytest.raises(ValidationError, match="virgule flottante"):
        EventEnvelope.model_validate_json(wire)
