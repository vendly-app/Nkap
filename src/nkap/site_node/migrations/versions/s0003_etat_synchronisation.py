"""État de la liaison avec le central (une seule ligne).

Revision ID: s0003
Revises: s0002
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from nkap.core.db_types import UTCDateTime

revision: str = "s0003"
down_revision: str | Sequence[str] | None = "s0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    state = op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("last_attempt_at", UTCDateTime(), nullable=True),
        sa.Column("last_success_at", UTCDateTime(), nullable=True),
        sa.Column("offline_since", UTCDateTime(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", UTCDateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("central_acked_through", sa.BigInteger(), nullable=False),
        sa.Column("last_server_time", UTCDateTime(), nullable=True),
        sa.Column("clock_offset_ms", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "consecutive_failures >= 0", name=op.f("ck_sync_state_failures_non_negative")
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_sync_state_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_state")),
    )
    op.bulk_insert(state, [{"id": 1, "consecutive_failures": 0, "central_acked_through": 0}])


def downgrade() -> None:
    op.drop_table("sync_state")
