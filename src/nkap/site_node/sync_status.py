"""État de la synchronisation, tel qu'affiché à l'utilisateur (bandeau, écran Synchronisation).

- ``synced`` : tout est acquitté par le central ;
- ``pending`` : des opérations attendent leur envoi (liaison normale) ;
- ``offline`` : central injoignable depuis ``offline_since`` (mode dégradé visible) ;
- ``error`` : un envoi est bloqué et demande une intervention (événement refusé, jeton...).

L'alerte d'horloge se déclenche si l'heure du PC s'écarte de plus de 10 minutes (réglable)
de celle du central, ou si elle est revenue en arrière depuis le dernier contact.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nkap.core.clock import Clock
from nkap.site_node.models import (
    OUTBOX_PENDING,
    OUTBOX_REJECTED,
    OutboxEvent,
    SyncStateRow,
)
from nkap.site_node.sequences import SYNC_SEQUENCE, current_value


class SyncStatusView(BaseModel):
    state: Literal["synced", "pending", "offline", "error"]
    pending_count: int
    rejected_count: int
    oldest_pending_at: datetime | None
    local_last_seq: int
    central_acked_through: int
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    offline_since: datetime | None
    next_attempt_at: datetime | None
    consecutive_failures: int
    last_error_code: str | None
    last_error_message: str | None
    clock_offset_seconds: int | None
    clock_alert: bool


def read_sync_status(
    session: Session, clock: Clock, tolerance: timedelta = timedelta(minutes=10)
) -> SyncStatusView:
    state = session.get(SyncStateRow, 1)
    if state is None:  # pragma: no cover - créé par la migration s0003
        raise RuntimeError("Ligne sync_state absente : migrations du site incomplètes.")

    def count(status: str) -> int:
        stmt = select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == status)
        return int(session.scalar(stmt) or 0)

    pending = count(OUTBOX_PENDING)
    rejected = count(OUTBOX_REJECTED)
    oldest = session.scalar(
        select(func.min(OutboxEvent.occurred_at)).where(
            OutboxEvent.status.in_((OUTBOX_PENDING, OUTBOX_REJECTED))
        )
    )

    offset = state.clock_offset_ms
    offset_seconds = None if offset is None else offset // 1000
    clock_alert = offset is not None and abs(offset) > tolerance // timedelta(milliseconds=1)
    if state.last_server_time is not None and clock.now() < state.last_server_time - tolerance:
        clock_alert = True  # l'heure du PC a reculé depuis le dernier contact

    blocked = rejected > 0 or (
        state.consecutive_failures > 0
        and state.offline_since is None
        and bool(state.last_error_code)
    )
    if blocked:
        view_state: Literal["synced", "pending", "offline", "error"] = "error"
    elif state.offline_since is not None:
        view_state = "offline"
    elif pending:
        view_state = "pending"
    else:
        view_state = "synced"

    return SyncStatusView(
        state=view_state,
        pending_count=pending + rejected,
        rejected_count=rejected,
        oldest_pending_at=oldest,
        local_last_seq=current_value(session, SYNC_SEQUENCE),
        central_acked_through=state.central_acked_through,
        last_attempt_at=state.last_attempt_at,
        last_success_at=state.last_success_at,
        offline_since=state.offline_since,
        next_attempt_at=state.next_attempt_at,
        consecutive_failures=state.consecutive_failures,
        last_error_code=state.last_error_code,
        last_error_message=state.last_error_message,
        clock_offset_seconds=offset_seconds,
        clock_alert=clock_alert,
    )
