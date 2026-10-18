"""Configuration du nœud de site (variables ``NKAP_SITE_*`` ou fichier ``.env``).

Le jeton de synchronisation est un secret : il n'est jamais écrit dans le code.
À l'étape 8 (installation Windows), il sera rangé dans le gestionnaire d'identifiants
de Windows (DPAPI) plutôt que dans un fichier.
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SiteSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NKAP_SITE_", env_file=".env", extra="ignore")

    database_url: str
    """Ex. ``sqlite:///C:/Nkap/data/site.db`` (disque local du nœud, jamais un partage)."""

    central_url: str | None = None
    """Ex. ``https://central.exemple.cm`` ; vide = synchronisation désactivée."""

    sync_token: SecretStr | None = None
    sync_interval_seconds: int = 60
    sync_batch_size: int = 200
    clock_drift_tolerance_minutes: int = 10

    host: str = "127.0.0.1"
    """Adresse d'écoute. Rester en local tant que l'authentification (étape 2) n'existe pas."""

    port: int = 8700
