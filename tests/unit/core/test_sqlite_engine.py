"""Réglages de sécurité de SQLite (mode WAL, BEGIN IMMEDIATE, lecteurs réseau...)."""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import URL, text

from nkap.core.db import (
    NetworkDatabasePathError,
    create_db_engine,
    ensure_local_database_path,
    sqlite_integrity_problems,
)


def test_connections_use_wal_full_sync_and_foreign_keys(sqlite_db_url: URL) -> None:
    engine = create_db_engine(sqlite_db_url)
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
        assert conn.execute(text("PRAGMA synchronous")).scalar_one() == 2  # FULL
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    engine.dispose()


def test_foreign_keys_can_be_disabled_for_migrations(sqlite_db_url: URL) -> None:
    engine = create_db_engine(sqlite_db_url, sqlite_foreign_keys=False)
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 0
    engine.dispose()


def test_in_memory_databases_are_refused() -> None:
    with pytest.raises(ValueError, match="fichier"):
        create_db_engine("sqlite://")
    with pytest.raises(ValueError, match="fichier"):
        create_db_engine("sqlite:///:memory:")


@pytest.mark.parametrize("path", [r"\\serveur\partage\nkap.db", "//serveur/partage/nkap.db"])
def test_network_paths_are_refused(path: str) -> None:
    with pytest.raises(NetworkDatabasePathError, match="lecteur réseau"):
        ensure_local_database_path(Path(path))
    with pytest.raises(NetworkDatabasePathError):
        create_db_engine(URL.create("sqlite+pysqlite", database=path))


def test_local_paths_are_accepted(tmp_path: Path) -> None:
    ensure_local_database_path(tmp_path / "nkap.db")


def test_every_transaction_reserves_the_write_lock_immediately(
    sqlite_db_url: URL,
) -> None:
    engine = create_db_engine(sqlite_db_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
    other = sqlite3.connect(str(sqlite_db_url.database), timeout=0.05, isolation_level=None)
    try:
        with engine.connect() as conn:
            conn.begin()
            # Aucune écriture n'a encore eu lieu, mais le verrou est déjà pris :
            # un autre écrivain doit attendre.
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("BEGIN IMMEDIATE")
            conn.rollback()
        other.execute("BEGIN IMMEDIATE")
        other.execute("ROLLBACK")
    finally:
        other.close()
        engine.dispose()


def test_commit_rollback_and_savepoints_behave_transactionally(sqlite_db_url: URL) -> None:
    engine = create_db_engine(sqlite_db_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO t VALUES (1)"))
        savepoint = conn.begin_nested()
        conn.execute(text("INSERT INTO t VALUES (2)"))
        savepoint.rollback()
        conn.execute(text("INSERT INTO t VALUES (3)"))
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO t VALUES (4)"))
        conn.rollback()
    with engine.connect() as conn:
        values = conn.execute(text("SELECT x FROM t ORDER BY x")).scalars().all()
    assert values == [1, 3]
    engine.dispose()


def test_transactional_ddl_is_rolled_back(sqlite_db_url: URL) -> None:
    engine = create_db_engine(sqlite_db_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
        conn.rollback()
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).all()
    assert tables == []
    engine.dispose()


def test_integrity_check_reports_a_healthy_database(sqlite_db_url: URL) -> None:
    engine = create_db_engine(sqlite_db_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
    assert sqlite_integrity_problems(engine) == []
    engine.dispose()
