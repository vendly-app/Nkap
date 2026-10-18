"""Migrations de schéma (Alembic), pilotées depuis le code.

Il existe deux jeux de migrations distincts (décision 006) :

- ``nkap.site_node:migrations`` pour la base d'un site ;
- ``nkap.central:migrations`` pour la base centrale.

Chacun est testé sur SQLite et sur PostgreSQL.
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import URL, make_url

from nkap.core.db import create_db_engine

SITE_MIGRATIONS = "nkap.site_node:migrations"
CENTRAL_MIGRATIONS = "nkap.central:migrations"


def make_alembic_config(script_location: str, url: str | URL) -> Config:
    config = Config()
    config.set_main_option("script_location", script_location)
    # L'URL passe par les attributs (et non par le texte de configuration) pour éviter
    # les problèmes d'échappement des mots de passe contenant « % ».
    config.attributes["database_url"] = make_url(url)
    return config


def upgrade_database(script_location: str, url: str | URL, revision: str = "head") -> None:
    """Met le schéma de la base à jour (jusqu'à la dernière version par défaut)."""
    command.upgrade(make_alembic_config(script_location, url), revision)


def downgrade_database(script_location: str, url: str | URL, revision: str) -> None:
    """Revient à une version antérieure du schéma (``base`` = base vide)."""
    command.downgrade(make_alembic_config(script_location, url), revision)


def current_revision(url: str | URL) -> str | None:
    """Version du schéma actuellement installée dans la base."""
    engine = create_db_engine(url)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
