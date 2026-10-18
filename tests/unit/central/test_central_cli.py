import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from nkap.central.auth import authenticate
from nkap.central.cli import main
from nkap.central.models import SyncSite
from nkap.core.db import create_db_engine, make_session_factory
from support.db import sqlite_url


def test_migrate_then_register_a_site_prints_its_token_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    url = sqlite_url(tmp_path / "central.db")
    monkeypatch.setenv("NKAP_CENTRAL_DATABASE_URL", url.render_as_string(hide_password=False))
    assert main(["migrate"]) == 0
    site_id, company_id = uuid.uuid4(), uuid.uuid4()
    args = ["register-site", "--site-id", str(site_id), "--company-id", str(company_id)]
    assert main([*args, "--site-code", "S01"]) == 0
    token = capsys.readouterr().out.strip().splitlines()[-1]

    engine = create_db_engine(url)
    try:
        with make_session_factory(engine)() as session:
            assert authenticate(session, token).site_id == site_id
            assert session.scalars(select(SyncSite.site_code)).all() == ["S01"]
    finally:
        engine.dispose()

    assert main(["revoke-site", "--site-id", str(site_id)]) == 0
    assert "révoqué" in capsys.readouterr().out
