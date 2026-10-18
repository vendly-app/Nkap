"""Configuration du central, lue dans les variables d'environnement (préfixe ``NKAP_CENTRAL_``)
ou dans le fichier ``.env``. Aucun secret dans le code (voir ``.env.example``).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class CentralSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NKAP_CENTRAL_", env_file=".env", extra="ignore")

    database_url: str
    """Ex. ``postgresql+psycopg://nkap:motdepasse@localhost:5432/nkap_central``."""

    host: str = "127.0.0.1"
    port: int = 8800
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
