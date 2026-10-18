"""Environnement Alembic de la base d'un site."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, make_url

from nkap.core.db import create_db_engine
from nkap.site_node.models import SiteBase

config = context.config
target_metadata = SiteBase.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite ne sait pas modifier une table en place : Alembic la recrée.
        render_as_batch=connection.dialect.name == "sqlite",
        # Notre moteur SQLite gère correctement les transactions sur le schéma :
        # une migration qui échoue est entièrement annulée.
        transactional_ddl=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.attributes.get("database_url") or make_url(
        config.get_main_option("sqlalchemy.url", "")
    )
    # Clés étrangères désactivées pendant la migration (recréation de tables SQLite),
    # puis vérifiées par les tests de migration.
    engine = create_db_engine(url, sqlite_foreign_keys=False)
    try:
        with engine.connect() as connection:
            _run(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Le mode hors connexion d'Alembic (génération de SQL) n'est pas utilisé.")
run_migrations_online()
