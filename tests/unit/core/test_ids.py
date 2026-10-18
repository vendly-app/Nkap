from datetime import UTC, datetime, timedelta

import pytest

from nkap.core.clock import FakeClock
from nkap.core.ids import uuid7, uuid7_timestamp


def test_uuid7_has_version_7_and_rfc_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert (value.int >> 62) & 0b11 == 0b10


def test_uuid7_embeds_the_clock_time_to_the_millisecond() -> None:
    at = datetime(2026, 10, 18, 8, 30, 15, 123456, tzinfo=UTC)
    value = uuid7(FakeClock(at))
    assert uuid7_timestamp(value) == at.replace(microsecond=123000)


def test_uuid7_is_unique_even_within_the_same_millisecond() -> None:
    clock = FakeClock(datetime(2026, 10, 18, 8, 0, tzinfo=UTC))
    values = {uuid7(clock) for _ in range(20_000)}
    assert len(values) == 20_000


def test_uuid7_sorts_by_time_across_milliseconds() -> None:
    clock = FakeClock(datetime(2026, 10, 18, 8, 0, tzinfo=UTC))
    first = uuid7(clock)
    clock.advance(timedelta(milliseconds=1))
    second = uuid7(clock)
    assert first.int < second.int


def test_uuid7_is_deterministic_with_injected_randomness() -> None:
    clock = FakeClock(datetime(2026, 10, 18, 8, 0, tzinfo=UTC))
    a = uuid7(clock, random_bytes=lambda n: b"\x00" * n)
    b = uuid7(clock, random_bytes=lambda n: b"\x00" * n)
    assert a == b


def test_uuid7_refuses_a_clock_before_1970() -> None:
    with pytest.raises(ValueError, match="plage"):
        uuid7(FakeClock(datetime(1960, 1, 1, tzinfo=UTC)))


def test_uuid7_timestamp_refuses_other_versions() -> None:
    import uuid

    with pytest.raises(ValueError, match="version 7"):
        uuid7_timestamp(uuid.uuid4())
