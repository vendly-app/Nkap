import uuid
from pathlib import Path

import pytest

from nkap.site_node.cli import main
from support.db import sqlite_url


@pytest.fixture
def site_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = sqlite_url(tmp_path / "site.db")
    monkeypatch.setenv("NKAP_SITE_DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.delenv("NKAP_SITE_CENTRAL_URL", raising=False)
    monkeypatch.delenv("NKAP_SITE_SYNC_TOKEN", raising=False)
    return tmp_path


def test_init_status_and_audit_check(site_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ids = ["--company-id", str(uuid.uuid4()), "--site-id", str(uuid.uuid4())]
    assert main(["init", *ids, "--site-code", "S01"]) == 0
    assert "Site S01 initialisé" in capsys.readouterr().out
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "État : synced" in out
    assert "jamais" in out
    assert main(["verify-audit"]) == 0
    assert "intègre" in capsys.readouterr().out
    assert main(["migrate"]) == 0


def test_sync_without_central_configuration_explains_why(
    site_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = ["--company-id", str(uuid.uuid4()), "--site-id", str(uuid.uuid4())]
    main(["init", *ids, "--site-code", "S01"])
    capsys.readouterr()
    assert main(["sync"]) == 1
    assert "NKAP_SITE_CENTRAL_URL" in capsys.readouterr().out
