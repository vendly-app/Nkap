"""Journal d'audit chaîné du site (ajout seul).

Revision ID: s0002
Revises: s0001
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from nkap.core.db_types import UTCDateTime

revision: str = "s0002"
down_revision: str | Sequence[str] | None = "s0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GENESIS_HASH = "0" * 64
_MSG_APPEND_ONLY = "audit_log - table en ajout seul (modification et suppression interdites)"
_MSG_CHAIN = "audit_log - chainage invalide (numero ou empreinte precedente)"
_MSG_HEAD = "audit_chain_head - la tete de chaine ne peut qu''avancer d''une ligne existante"


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("chain_seq", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", UTCDateTime(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_label", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("chain_seq", name=op.f("pk_audit_log")),
        sa.UniqueConstraint("audit_id", name=op.f("uq_audit_log_audit_id")),
        sa.UniqueConstraint("hash", name=op.f("uq_audit_log_hash")),
    )
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index(op.f("ix_audit_log_occurred_at"), "audit_log", ["occurred_at"])

    head = op.create_table(
        "audit_chain_head",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("last_seq", sa.BigInteger(), nullable=False),
        sa.Column("last_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_audit_chain_head_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_chain_head")),
    )
    op.bulk_insert(head, [{"id": 1, "last_seq": 0, "last_hash": GENESIS_HASH}])

    _create_guards()


def downgrade() -> None:
    _drop_guards()
    op.drop_table("audit_chain_head")
    op.drop_index(op.f("ix_audit_log_occurred_at"), table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_actor_id"), table_name="audit_log")
    op.drop_table("audit_log")


def _create_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for event in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_audit_log_no_{event.lower()} BEFORE {event} ON audit_log "
                f"BEGIN SELECT RAISE(ABORT, '{_MSG_APPEND_ONLY}'); END"
            )
        op.execute(
            "CREATE TRIGGER trg_audit_log_chain BEFORE INSERT ON audit_log "
            "WHEN NEW.chain_seq <> (SELECT last_seq + 1 FROM audit_chain_head WHERE id = 1) "
            "OR NEW.prev_hash <> (SELECT last_hash FROM audit_chain_head WHERE id = 1) "
            f"BEGIN SELECT RAISE(ABORT, '{_MSG_CHAIN}'); END"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_chain_head_forward BEFORE UPDATE ON audit_chain_head "
            "WHEN NEW.id <> OLD.id OR NEW.last_seq <> OLD.last_seq + 1 "
            "OR NEW.last_hash IS NOT (SELECT hash FROM audit_log WHERE chain_seq = NEW.last_seq) "
            f"BEGIN SELECT RAISE(ABORT, '{_MSG_HEAD}'); END"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_chain_head_no_delete BEFORE DELETE ON audit_chain_head "
            f"BEGIN SELECT RAISE(ABORT, '{_MSG_HEAD}'); END"
        )
    elif dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION nkap_append_only_guard() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN RAISE EXCEPTION USING MESSAGE = '{_MSG_APPEND_ONLY}'; END $$"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
            "FOR EACH ROW EXECUTE FUNCTION nkap_append_only_guard()"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
            "FOR EACH STATEMENT EXECUTE FUNCTION nkap_append_only_guard()"
        )
        op.execute(
            "CREATE FUNCTION nkap_audit_chain_guard() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "DECLARE head_seq BIGINT; head_hash VARCHAR(64); "
            "BEGIN "
            "SELECT last_seq, last_hash INTO head_seq, head_hash "
            "FROM audit_chain_head WHERE id = 1; "
            "IF NEW.chain_seq <> head_seq + 1 OR NEW.prev_hash <> head_hash THEN "
            f"RAISE EXCEPTION USING MESSAGE = '{_MSG_CHAIN}'; "
            "END IF; "
            "RETURN NEW; "
            "END $$"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_log_chain BEFORE INSERT ON audit_log "
            "FOR EACH ROW EXECUTE FUNCTION nkap_audit_chain_guard()"
        )
        op.execute(
            "CREATE FUNCTION nkap_audit_head_guard() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN "
            "IF TG_OP = 'DELETE' THEN "
            f"RAISE EXCEPTION USING MESSAGE = '{_MSG_HEAD}'; "
            "END IF; "
            "IF NEW.id <> OLD.id OR NEW.last_seq <> OLD.last_seq + 1 "
            "OR NEW.last_hash IS DISTINCT FROM "
            "(SELECT hash FROM audit_log WHERE chain_seq = NEW.last_seq) THEN "
            f"RAISE EXCEPTION USING MESSAGE = '{_MSG_HEAD}'; "
            "END IF; "
            "RETURN NEW; "
            "END $$"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_chain_head_guard BEFORE UPDATE OR DELETE "
            "ON audit_chain_head FOR EACH ROW EXECUTE FUNCTION nkap_audit_head_guard()"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_chain_head_no_truncate BEFORE TRUNCATE ON audit_chain_head "
            "FOR EACH STATEMENT EXECUTE FUNCTION nkap_append_only_guard()"
        )
    else:  # pragma: no cover - moteur non prévu
        raise RuntimeError(f"Moteur non pris en charge : {dialect}")


def _drop_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for name in (
            "trg_audit_chain_head_no_delete",
            "trg_audit_chain_head_forward",
            "trg_audit_log_chain",
            "trg_audit_log_no_delete",
            "trg_audit_log_no_update",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_chain_head_no_truncate ON audit_chain_head")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_chain_head_guard ON audit_chain_head")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_chain ON audit_log")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_truncate ON audit_log")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log")
        op.execute("DROP FUNCTION IF EXISTS nkap_audit_head_guard()")
        op.execute("DROP FUNCTION IF EXISTS nkap_audit_chain_guard()")
        op.execute("DROP FUNCTION IF EXISTS nkap_append_only_guard()")
