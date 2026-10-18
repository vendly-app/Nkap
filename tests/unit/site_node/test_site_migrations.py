"""Les migrations du site fonctionnent sur SQLite et PostgreSQL, dans les deux sens."""

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, inspect, text

from nkap.core.db import create_db_engine, sqlite_integrity_problems
from nkap.core.migrations import (
    SITE_MIGRATIONS,
    current_revision,
    downgrade_database,
    make_alembic_config,
    upgrade_database,
)
from nkap.site_node.models import SiteBase

EXPECTED_TABLES = {"node_identity", "site_sequences", "sync_outbox", "demo_notes"}


def _head() -> str:
    script = ScriptDirectory.from_config(make_alembic_config(SITE_MIGRATIONS, "sqlite:///x.db"))
    head = script.get_current_head()
    assert head is not None
    return head


def _tables(url: URL) -> set[str]:
    engine = create_db_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def _triggers(url: URL) -> set[str]:
    engine = create_db_engine(url)
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                sql = "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            else:
                sql = "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
            return set(conn.execute(text(sql)).scalars())
    finally:
        engine.dispose()


def test_upgrade_creates_the_schema_and_downgrade_removes_it(db_url: URL) -> None:
    upgrade_database(SITE_MIGRATIONS, db_url)
    assert current_revision(db_url) == _head()
    assert _tables(db_url) == EXPECTED_TABLES
    downgrade_database(SITE_MIGRATIONS, db_url, "base")
    assert _tables(db_url) == set()
    assert _triggers(db_url) == set()
    upgrade_database(SITE_MIGRATIONS, db_url)
    assert _tables(db_url) == EXPECTED_TABLES


def test_migrated_schema_matches_the_models_exactly(db_url: URL) -> None:
    upgrade_database(SITE_MIGRATIONS, db_url)
    engine = create_db_engine(db_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            differences = compare_metadata(context, SiteBase.metadata)
    finally:
        engine.dispose()
    assert differences == []


def test_protection_triggers_are_installed(db_url: URL) -> None:
    upgrade_database(SITE_MIGRATIONS, db_url)
    triggers = _triggers(db_url)
    if db_url.get_backend_name() == "sqlite":
        assert triggers == {"trg_sync_outbox_immutable", "trg_sync_outbox_no_delete_unacked"}
    else:
        assert triggers == {"trg_sync_outbox_guard"}


def test_event_counter_exists_from_installation(db_url: URL) -> None:
    upgrade_database(SITE_MIGRATIONS, db_url)
    engine = create_db_engine(db_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT name, last_value FROM site_sequences")).all()
    finally:
        engine.dispose()
    assert [tuple(r) for r in rows] == [("sync", 0)]


def test_sqlite_database_is_healthy_after_migrations(sqlite_db_url: URL) -> None:
    upgrade_database(SITE_MIGRATIONS, sqlite_db_url)
    engine = create_db_engine(sqlite_db_url)
    try:
        assert sqlite_integrity_problems(engine) == []
    finally:
        engine.dispose()
