from datetime import UTC, date, datetime, timedelta

import pytest

from nkap.core.clock import FakeClock, SystemClock, local_date, require_aware


def test_system_clock_returns_utc_aware_datetime() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_fake_clock_can_be_advanced_moved_back_and_set() -> None:
    start = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)
    clock = FakeClock(start)
    assert clock.now() == start
    clock.advance(timedelta(days=2))
    assert clock.now() == start + timedelta(days=2)
    clock.advance(timedelta(days=-3))
    assert clock.now() == start - timedelta(days=1)
    clock.set(datetime(2030, 1, 1, tzinfo=UTC))
    assert clock.now().year == 2030


def test_naive_datetimes_are_refused() -> None:
    naive = datetime(2026, 10, 18, 8, 0)  # noqa: DTZ001 - volontairement sans fuseau
    with pytest.raises(ValueError, match="sans fuseau"):
        require_aware(naive)
    with pytest.raises(ValueError, match="sans fuseau"):
        FakeClock(naive)


def test_local_date_uses_site_timezone() -> None:
    # 23h30 UTC = 00h30 le lendemain à Douala (UTC+1).
    clock = FakeClock(datetime(2026, 10, 18, 23, 30, tzinfo=UTC))
    assert local_date(clock, "Africa/Douala") == date(2026, 10, 19)
    assert local_date(clock, "UTC") == date(2026, 10, 18)
