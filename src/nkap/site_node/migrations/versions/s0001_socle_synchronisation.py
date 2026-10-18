"""Socle de synchronisation du site : identité, compteurs, outbox, notes factices.

Revision ID: s0001
Revises:
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from nkap.core.db_types import UTCDateTime

revision: str = "s0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Colonnes qui décrivent l'événement lui-même : elles ne doivent jamais changer.
_OUTBOX_CONTENT_COLUMNS = (
    "event_id, site_seq, tx_id, tx_size, event_type, payload_version, company_id, site_id, "
    "entity_type, entity_id, entity_version, occurred_at, business_date, created_by, "
    "payload, fingerprint"
)
_MSG_IMMUTABLE = "sync_outbox - le contenu d''un evenement est immuable"
_MSG_NO_DELETE = "sync_outbox - un evenement non acquitte ne peut pas etre supprime"


def upgrade() -> None:
    op.create_table(
        "node_identity",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("site_code", sa.String(length=16), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_node_identity_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_node_identity")),
    )

    sequences = op.create_table(
        "site_sequences",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("last_value", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("last_value >= 0", name=op.f("ck_site_sequences_non_negative")),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_site_sequences")),
    )
    # Le compteur des événements existe dès l'installation.
    op.bulk_insert(sequences, [{"name": "sync", "last_value": 0}])

    op.create_table(
        "sync_outbox",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("site_seq", sa.BigInteger(), nullable=False),
        sa.Column("tx_id", sa.Uuid(), nullable=False),
        sa.Column("tx_size", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("entity_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", UTCDateTime(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_attempt_at", UTCDateTime(), nullable=True),
        sa.Column("acked_at", UTCDateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.CheckConstraint("site_seq > 0", name=op.f("ck_sync_outbox_site_seq_positive")),
        sa.CheckConstraint("tx_size > 0", name=op.f("ck_sync_outbox_tx_size_positive")),
        sa.CheckConstraint(
            "status IN ('pending', 'acked', 'rejected')", name=op.f("ck_sync_outbox_status_valid")
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_sync_outbox")),
        sa.UniqueConstraint("site_seq", name=op.f("uq_sync_outbox_site_seq")),
    )
    op.create_index("ix_sync_outbox_entity", "sync_outbox", ["entity_type", "entity_id"])
    op.create_index("ix_sync_outbox_status_seq", "sync_outbox", ["status", "site_seq"])
    op.create_index(op.f("ix_sync_outbox_tx_id"), "sync_outbox", ["tx_id"])

    op.create_table(
        "demo_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sync_status", sa.String(length=16), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 1", name=op.f("ck_demo_notes_version_positive")),
        sa.CheckConstraint(
            "sync_status IN ('pending', 'synced', 'error')",
            name=op.f("ck_demo_notes_sync_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_demo_notes")),
    )

    _create_outbox_guards()


def downgrade() -> None:
    _drop_outbox_guards()
    op.drop_table("demo_notes")
    op.drop_index(op.f("ix_sync_outbox_tx_id"), table_name="sync_outbox")
    op.drop_index("ix_sync_outbox_status_seq", table_name="sync_outbox")
    op.drop_index("ix_sync_outbox_entity", table_name="sync_outbox")
    op.drop_table("sync_outbox")
    op.drop_table("site_sequences")
    op.drop_table("node_identity")


def _create_outbox_guards() -> None:
    """Déclencheurs : contenu des événements immuable, pas de suppression avant accusé."""
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            f"CREATE TRIGGER trg_sync_outbox_immutable "
            f"BEFORE UPDATE OF {_OUTBOX_CONTENT_COLUMNS} ON sync_outbox "
            f"BEGIN SELECT RAISE(ABORT, '{_MSG_IMMUTABLE}'); END"
        )
        op.execute(
            "CREATE TRIGGER trg_sync_outbox_no_delete_unacked "
            "BEFORE DELETE ON sync_outbox WHEN OLD.status <> 'acked' "
            f"BEGIN SELECT RAISE(ABORT, '{_MSG_NO_DELETE}'); END"
        )
    elif dialect == "postgresql":
        new_cols = ", ".join(f"NEW.{c.strip()}" for c in _OUTBOX_CONTENT_COLUMNS.split(","))
        old_cols = ", ".join(f"OLD.{c.strip()}" for c in _OUTBOX_CONTENT_COLUMNS.split(","))
        op.execute(
            "CREATE FUNCTION nkap_sync_outbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN "
            "IF TG_OP = 'DELETE' THEN "
            f"IF OLD.status <> 'acked' THEN RAISE EXCEPTION '{_MSG_NO_DELETE}'; END IF; "
            "RETURN OLD; "
            "END IF; "
            f"IF ({new_cols}) IS DISTINCT FROM ({old_cols}) THEN "
            f"RAISE EXCEPTION '{_MSG_IMMUTABLE}'; "
            "END IF; "
            "RETURN NEW; "
            "END $$"
        )
        op.execute(
            "CREATE TRIGGER trg_sync_outbox_guard BEFORE UPDATE OR DELETE ON sync_outbox "
            "FOR EACH ROW EXECUTE FUNCTION nkap_sync_outbox_guard()"
        )
    else:  # pragma: no cover - moteur non prévu
        raise RuntimeError(f"Moteur non pris en charge : {dialect}")


def _drop_outbox_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_sync_outbox_no_delete_unacked")
        op.execute("DROP TRIGGER IF EXISTS trg_sync_outbox_immutable")
    elif dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_sync_outbox_guard ON sync_outbox")
        op.execute("DROP FUNCTION IF EXISTS nkap_sync_outbox_guard()")
