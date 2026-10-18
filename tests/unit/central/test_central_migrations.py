from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import URL, inspect, text

from nkap.central.models import CentralBase
from nkap.core.db import create_db_engine
from nkap.core.migrations import CENTRAL_MIGRATIONS, downgrade_database, upgrade_database

EXPECTED_TABLES = {
    "sync_sites",
    "sync_site_states",
    "sync_inbox",
    "demo_notes",
    "site_audit_entries",
    "audit_log",
    "audit_chain_head",
}
APPEND_ONLY = ("sync_inbox", "site_audit_entries", "audit_log")


def _inspect(url: URL) -> tuple[set[str], set[str]]:
    engine = create_db_engine(url)
    try:
        tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
        with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                sql = "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            else:
                sql = "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
            triggers = set(conn.execute(text(sql)).scalars())
        return tables, triggers
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(db_url: URL) -> None:
    upgrade_database(CENTRAL_MIGRATIONS, db_url)
    assert _inspect(db_url)[0] == EXPECTED_TABLES
    downgrade_database(CENTRAL_MIGRATIONS, db_url, "base")
    assert _inspect(db_url) == (set(), set())
    upgrade_database(CENTRAL_MIGRATIONS, db_url)
    assert _inspect(db_url)[0] == EXPECTED_TABLES


def test_migrated_schema_matches_the_models_exactly(db_url: URL) -> None:
    upgrade_database(CENTRAL_MIGRATIONS, db_url)
    engine = create_db_engine(db_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            assert compare_metadata(context, CentralBase.metadata) == []
    finally:
        engine.dispose()


def test_append_only_protections_are_installed(db_url: URL) -> None:
    upgrade_database(CENTRAL_MIGRATIONS, db_url)
    triggers = _inspect(db_url)[1]
    if db_url.get_backend_name() == "sqlite":
        expected = {f"trg_{t}_no_{e}" for t in APPEND_ONLY for e in ("update", "delete")}
        expected |= {
            "trg_audit_log_chain",
            "trg_audit_chain_head_forward",
            "trg_audit_chain_head_no_delete",
        }
    else:
        expected = {f"trg_{t}_{s}" for t in APPEND_ONLY for s in ("append_only", "no_truncate")}
        expected |= {
            "trg_audit_log_chain",
            "trg_audit_chain_head_guard",
            "trg_audit_chain_head_no_truncate",
        }
    assert triggers == expected
