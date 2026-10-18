"""Conventions communes aux modèles de données (site et central)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import MetaData

# Noms de contraintes et d'index prévisibles : indispensable pour que les migrations
# Alembic puissent les retrouver et les modifier, sur SQLite comme sur PostgreSQL.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def make_metadata() -> MetaData:
    return MetaData(naming_convention=NAMING_CONVENTION)


@dataclass(frozen=True, slots=True)
class Actor:
    """Auteur d'une opération (utilisateur connecté, ou le système lui-même)."""

    user_id: UUID | None
    label: str

    @classmethod
    def system(cls) -> Actor:
        return cls(user_id=None, label="système")
