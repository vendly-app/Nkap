"""Le banc de simulation lui-même : plusieurs sites, coupures, horloges indépendantes."""

from datetime import timedelta

import pytest

from support.bench import Bench


def test_two_sites_converge_on_the_central(bench: Bench) -> None:
    s1, s2 = bench.add_site("S01"), bench.add_site("S02")
    s1.create_notes(3)
    s2.create_notes(2)
    bench.sync_all()
    bench.assert_converged()
    assert bench.central_note_count() == 5


def test_a_site_offline_does_not_prevent_the_others(bench: Bench) -> None:
    s1, s2 = bench.add_site("S01"), bench.add_site("S02")
    s2.go_offline()
    s1.create_notes(2)
    s2.create_notes(2)
    bench.sync_all()
    assert bench.central_note_count() == 2
    assert s2.status().state == "offline"
    bench.advance(timedelta(days=3))
    s2.go_online()
    bench.sync_all()
    bench.assert_converged()
    assert bench.central_note_count() == 4


def test_convergence_check_detects_unsent_data(bench: Bench) -> None:
    site = bench.add_site("S01")
    site.create_notes(1)
    with pytest.raises(AssertionError, match="non acquitté"):
        bench.assert_converged()


def test_each_site_has_its_own_clock(bench: Bench) -> None:
    s1, s2 = bench.add_site("S01"), bench.add_site("S02")
    s2.clock.advance(timedelta(days=-2))
    assert s1.clock.now() - s2.clock.now() == timedelta(days=2)
