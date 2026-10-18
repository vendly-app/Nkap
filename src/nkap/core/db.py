"""Connexion aux bases de données (SQLite pour un site, PostgreSQL pour le central).

Réglages SQLite appliqués à chaque connexion (décision 001) :

- **Mode WAL** : les lectures ne bloquent pas les écritures, et la base résiste mieux
  aux arrêts brutaux.
- **synchronous=FULL** : une opération confirmée est réellement écrite sur le disque,
  même en cas de coupure de courant juste après (au prix d'un peu de vitesse).
- **Clés étrangères vérifiées** (désactivables uniquement pendant les migrations).
- **BEGIN IMMEDIATE** : chaque transaction réserve l'écriture dès son début. Deux
  opérations ne peuvent donc jamais se croiser (pas de compteur lu deux fois, pas
  d'erreur « base verrouillée » au milieu d'une écriture).
- **Refus des lecteurs réseau** : une base SQLite partagée par le réseau se corrompt.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import URL, Connection, Engine, create_engine, event, make_url, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

SQLITE_BUSY_TIMEOUT_MS = 10_000
"""Temps d'attente maximal (millisecondes) quand une autre écriture est en cours."""

_DRIVE_REMOTE = 4  # valeur Windows de GetDriveTypeW pour un lecteur réseau


class NetworkDatabasePathError(RuntimeError):
    """Base SQLite placée sur un lecteur réseau : interdit (risque de corruption)."""


def ensure_local_database_path(path: Path) -> None:
    """Refuse un chemin de base SQLite situé sur un partage ou un lecteur réseau."""
    raw = str(path)
    message = (
        f"La base {raw} est sur un lecteur réseau. Une base SQLite doit rester sur un "
        "disque local du nœud de site (risque de corruption)."
    )
    if raw.startswith(("\\\\", "//")):
        raise NetworkDatabasePathError(message)
    if sys.platform == "win32":
        import ctypes

        drive, _ = os.path.splitdrive(os.path.abspath(raw))
        if drive.startswith("\\\\"):
            raise NetworkDatabasePathError(message)
        if drive and ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == _DRIVE_REMOTE:
            raise NetworkDatabasePathError(message)


def create_db_engine(
    url: str | URL,
    *,
    sqlite_foreign_keys: bool = True,
    echo: bool = False,
) -> Engine:
    """Crée la connexion à une base (SQLite ou PostgreSQL) avec les bons réglages."""
    url_obj = make_url(url)
    if url_obj.get_backend_name() == "sqlite":
        return _create_sqlite_engine(url_obj, foreign_keys=sqlite_foreign_keys, echo=echo)
    return create_engine(url_obj, echo=echo, pool_pre_ping=True)


def _create_sqlite_engine(url: URL, *, foreign_keys: bool, echo: bool) -> Engine:
    database = url.database
    if not database or database == ":memory:" or url.query.get("mode") == "memory":
        raise ValueError("SQLite doit utiliser un fichier : le mode WAL est impossible en mémoire.")
    ensure_local_database_path(Path(database))

    engine = create_engine(
        url,
        echo=echo,
        connect_args={
            "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000,
            "check_same_thread": False,
            # Python 3.12 : mode de transaction « historique », que nous pilotons
            # nous-mêmes ci-dessous (recette documentée par SQLAlchemy).
            "autocommit": sqlite3.LEGACY_TRANSACTION_CONTROL,
        },
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: ConnectionPoolEntry) -> None:
        # Le pilote sqlite3 n'émet plus de BEGIN de lui-même : c'est _on_begin qui le fait.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise RuntimeError(f"Impossible d'activer le mode WAL (mode obtenu : {mode}).")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Fabrique de sessions. Usage : ``with factory.begin() as session: ...``."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def sqlite_integrity_problems(engine: Engine) -> list[str]:
    """Lance ``PRAGMA integrity_check`` et renvoie les problèmes (liste vide si tout va bien)."""
    with engine.connect() as conn:
        rows = [str(row[0]) for row in conn.execute(text("PRAGMA integrity_check"))]
        fk_rows = list(conn.execute(text("PRAGMA foreign_key_check")))
    problems = [row for row in rows if row.lower() != "ok"]
    problems.extend(f"clé étrangère invalide : {tuple(row)}" for row in fk_rows)
    return problems
