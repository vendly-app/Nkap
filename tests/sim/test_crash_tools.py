"""L'outil qui tue un processus en pleine écriture fonctionne (utilisé par T17)."""

from pathlib import Path

from nkap.core.clock import FakeClock
from support import crash
from support.db import sqlite_url
from support.site import open_site_db


def test_a_child_process_can_die_in_the_middle_of_a_transaction(
    tmp_path: Path, clock: FakeClock
) -> None:
    url = sqlite_url(tmp_path / "site.db")
    open_site_db(url, clock).close()
    assert crash.run_until_exit("die-in-transaction", url) == crash.KILLED_EXIT_CODE


def test_a_child_process_can_be_killed_while_writing(tmp_path: Path, clock: FakeClock) -> None:
    url = sqlite_url(tmp_path / "site.db")
    open_site_db(url, clock).close()
    process = crash.start("write-forever", url)
    crash.wait_ready(process)
    crash.kill(process)
    assert process.returncode != 0
