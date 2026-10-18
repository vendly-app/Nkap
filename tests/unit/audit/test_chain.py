import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

from nkap.audit.chain import GENESIS_HASH, AuditContent, normalize_details, verify_chain

START = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)


def _chain(length: int) -> list[tuple[AuditContent, str]]:
    entries: list[tuple[AuditContent, str]] = []
    prev = GENESIS_HASH
    for seq in range(1, length + 1):
        content = AuditContent(
            chain_seq=seq,
            audit_id=uuid.uuid4(),
            occurred_at=START + timedelta(minutes=seq),
            site_id=uuid.uuid4(),
            actor_id=None,
            actor_label="système",
            action="demo_note.create",
            entity_type="demo_note",
            entity_id=uuid.uuid4(),
            details=normalize_details({"text": f"note {seq}"}),
            prev_hash=prev,
        )
        prev = content.compute_hash()
        entries.append((content, prev))
    return entries


def test_a_well_formed_chain_is_valid() -> None:
    result = verify_chain(_chain(5))
    assert result.ok
    assert result.checked == 5
    assert verify_chain([]).ok


def test_hash_is_deterministic_and_covers_every_field() -> None:
    content, digest = _chain(1)[0]
    assert content.compute_hash() == digest
    for field, value in [
        ("actor_label", "pirate"),
        ("details", {"text": "falsifié"}),
        ("occurred_at", START),
        ("prev_hash", "f" * 64),
        ("entity_id", uuid.uuid4()),
    ]:
        assert dataclasses.replace(content, **{field: value}).compute_hash() != digest


def test_a_modified_entry_is_detected() -> None:
    entries = _chain(5)
    content, digest = entries[2]
    entries[2] = (dataclasses.replace(content, details={"text": "falsifié"}), digest)
    result = verify_chain(entries)
    assert not result.ok
    assert result.first_broken_seq == 3
    assert result.reason == "ligne modifiée"


def test_a_recomputed_entry_breaks_the_link_with_the_next_one() -> None:
    entries = _chain(5)
    content, _ = entries[2]
    forged = dataclasses.replace(content, details={"text": "falsifié"})
    entries[2] = (forged, forged.compute_hash())  # le fraudeur recalcule l'empreinte...
    result = verify_chain(entries)
    assert not result.ok
    assert result.first_broken_seq == 4  # ... mais la ligne suivante ne pointe plus dessus
    assert result.reason == "chaînage rompu"


def test_deleted_or_reordered_entries_are_detected() -> None:
    entries = _chain(5)
    assert verify_chain(entries[:2] + entries[3:]).first_broken_seq == 4
    swapped = [entries[0], entries[2], entries[1], *entries[3:]]
    assert verify_chain(swapped).first_broken_seq == 3


def test_verification_can_start_in_the_middle_of_a_chain() -> None:
    entries = _chain(5)
    result = verify_chain(entries[2:], start_seq=3, start_prev_hash=entries[1][1])
    assert result.ok
    assert result.checked == 3


def test_details_are_normalized_like_after_a_database_round_trip() -> None:
    from decimal import Decimal

    assert normalize_details({"q": Decimal("1.50"), "d": START}) == {
        "d": "2026-10-18T08:00:00.000000Z",
        "q": "1.5",
    }
    assert normalize_details(None) == {}
