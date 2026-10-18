"""Envoi des événements du site vers le central (décision 008).

Un « passage » de synchronisation (``sync_once``) :

1. lit les événements non acquittés, dans l'ordre de ``site_seq``, par lots qui ne
   coupent jamais une transaction en deux ;
2. les envoie au central ;
3. marque « acquittés » ceux que le central confirme (``acked_through``), et seulement
   ceux-là ; les données concernées passent alors à « synchronisé » ;
4. recommence jusqu'à ce qu'il n'y ait plus rien à envoyer.

En cas d'échec, l'état est enregistré (hors ligne depuis, nombre d'échecs, prochaine
tentative) et la tentative suivante est retardée de plus en plus (2 s, 4 s, 8 s... jusqu'à
5 minutes) pour ne pas saturer une liaison fragile.

Aucune transaction de base n'est ouverte pendant l'appel réseau : la saisie sur le site
n'est jamais bloquée par une synchronisation lente.
"""

from __future__ import annotations

import logging
import random
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, exists, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from nkap.core.clock import Clock
from nkap.core.errors import NkapError
from nkap.events.envelope import EventEnvelope
from nkap.site_node.gateway import CentralGateway, CentralRefusedError, CentralUnavailableError
from nkap.site_node.identity import load_identity
from nkap.site_node.models import (
    OUTBOX_ACKED,
    OUTBOX_PENDING,
    OUTBOX_REJECTED,
    SYNC_ERROR,
    SYNC_PENDING,
    SYNC_SYNCED,
    SYNCABLE_ENTITIES,
    OutboxEvent,
    SyncStateRow,
)
from nkap.site_node.outbox import OutboxCorruptedError, envelope_from_outbox_row
from nkap.sync.protocol import PROTOCOL_VERSION, PushRequest, PushResponse, PushStatus

logger = logging.getLogger(__name__)

_NO_SYNC: dict[str, Any] = {"synchronize_session": False}
_UNACKED = (OUTBOX_PENDING, OUTBOX_REJECTED)


@dataclass(frozen=True, slots=True)
class SyncSettings:
    batch_size: int = 200
    """Nombre d'événements visé par lot (une transaction n'est jamais coupée)."""
    backoff_base_ms: int = 2_000
    backoff_max_ms: int = 300_000
    max_batches_per_run: int = 100
    clock_drift_tolerance: timedelta = timedelta(minutes=10)


class RunStatus(StrEnum):
    SYNCED = "synced"  # plus rien à envoyer : tout est acquitté par le central
    PARTIAL = "partial"  # progression, mais il reste des événements (passage suivant)
    WAITING = "waiting"  # attente avant la prochaine tentative
    BUSY = "busy"  # un autre passage est déjà en cours
    OFFLINE = "offline"  # central injoignable
    REFUSED = "refused"  # le central refuse la requête (jeton, droits...)
    REJECTED = "rejected"  # un événement est refusé : envoi bloqué à cet endroit
    CONFLICT = "conflict"  # anomalie grave signalée par le central
    ERROR = "error"  # problème local (file d'envoi altérée, événements manquants)


@dataclass(frozen=True, slots=True)
class SyncRunResult:
    status: RunStatus
    sent: int = 0
    acked: int = 0
    pending: int = 0
    error_code: str | None = None
    error_message: str | None = None


class SyncSender:
    """Envoie la file d'attente du site au central."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        gateway: CentralGateway,
        clock: Clock,
        settings: SyncSettings | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._gateway = gateway
        self._clock = clock
        self.settings = settings or SyncSettings()
        self._rng = rng or random.Random()  # noqa: S311 - aléa de temporisation, pas de sécurité
        self._lock = threading.Lock()

    # --- Point d'entrée ------------------------------------------------------------

    def sync_once(self, *, force: bool = False) -> SyncRunResult:
        """Un passage de synchronisation. ``force`` ignore l'attente entre deux tentatives."""
        if not self._lock.acquire(blocking=False):
            return SyncRunResult(RunStatus.BUSY, pending=self.pending_count())
        try:
            return self._run(force=force)
        finally:
            self._lock.release()

    def pending_count(self) -> int:
        with self._session_factory() as session:
            return _count_unacked(session)

    # --- Déroulement d'un passage ---------------------------------------------------

    def _run(self, *, force: bool) -> SyncRunResult:
        if not force and self._must_wait():
            return SyncRunResult(RunStatus.WAITING, pending=self.pending_count())
        sent = acked = 0
        for _ in range(self.settings.max_batches_per_run):
            try:
                site_id, batch = self._load_batch()
            except OutboxCorruptedError as exc:
                self._record_failure([], exc.code, exc.message(), offline=False)
                return self._result(RunStatus.ERROR, sent, acked, exc)

            if not batch:
                if sent:  # le central vient de répondre : pas besoin de l'interroger
                    return self._result(RunStatus.SYNCED, sent, acked)
                reopened = self._heartbeat()
                if isinstance(reopened, SyncRunResult):
                    return reopened
                if reopened:
                    continue  # le central a perdu des événements : on les renvoie
                return self._result(RunStatus.SYNCED, sent, acked)

            started = self._clock.now()
            try:
                response = self._gateway.push(
                    PushRequest(protocol_version=PROTOCOL_VERSION, site_id=site_id, events=batch)
                )
            except CentralUnavailableError as exc:
                self._record_failure(batch, exc.code, exc.message(), offline=True)
                return self._result(RunStatus.OFFLINE, sent, acked, exc)
            except CentralRefusedError as exc:
                self._record_failure(batch, exc.remote_code, exc.message(), offline=False)
                return self._result(RunStatus.REFUSED, sent, acked, exc, code=exc.remote_code)
            sent += len(batch)
            newly_acked, reopened = self._apply_response(batch, response, started)
            acked += newly_acked

            if response.status is PushStatus.OK:
                continue
            if response.status is PushStatus.GAP:
                if reopened:
                    continue
                error = NkapError("sync.central_behind", expected=response.expected_next)
                self._record_failure([], error.code, error.message(), offline=False)
                return self._result(RunStatus.ERROR, sent, acked, error)
            rejected = response.rejected
            if response.status is PushStatus.CONFLICT:
                status = RunStatus.CONFLICT
            else:
                status = RunStatus.REJECTED
            return SyncRunResult(
                status,
                sent,
                acked,
                self.pending_count(),
                rejected.code if rejected else None,
                rejected.message if rejected else None,
            )
        return self._result(RunStatus.PARTIAL, sent, acked)

    def _result(
        self,
        status: RunStatus,
        sent: int,
        acked: int,
        error: NkapError | None = None,
        *,
        code: str | None = None,
    ) -> SyncRunResult:
        return SyncRunResult(
            status,
            sent,
            acked,
            self.pending_count(),
            code or (error.code if error else None),
            error.message() if error else None,
        )

    def _must_wait(self) -> bool:
        with self._session_factory() as session:
            state = _state(session)
            return state.next_attempt_at is not None and self._clock.now() < state.next_attempt_at

    def _load_batch(self) -> tuple[UUID, list[EventEnvelope]]:
        """Prochain lot à envoyer : les plus anciens événements non acquittés."""
        with self._session_factory() as session:
            site_id = load_identity(session).site_id
            rows = list(
                session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.status.in_(_UNACKED))
                    .order_by(OutboxEvent.site_seq)
                    .limit(self.settings.batch_size)
                )
            )
            if rows:
                # Ne jamais couper une transaction : on complète la dernière.
                last = rows[-1]
                rows += session.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.tx_id == last.tx_id,
                        OutboxEvent.site_seq > last.site_seq,
                        OutboxEvent.status.in_(_UNACKED),
                    )
                    .order_by(OutboxEvent.site_seq)
                )
            return site_id, [envelope_from_outbox_row(row) for row in rows]

    def _heartbeat(self) -> int | SyncRunResult:
        """Rien à envoyer : on prend des nouvelles du central (liaison, horloge, retard)."""
        started = self._clock.now()
        try:
            remote = self._gateway.fetch_state()
        except CentralUnavailableError as exc:
            self._record_failure([], exc.code, exc.message(), offline=True)
            return self._result(RunStatus.OFFLINE, 0, 0, exc)
        except CentralRefusedError as exc:
            self._record_failure([], exc.remote_code, exc.message(), offline=False)
            return self._result(RunStatus.REFUSED, 0, 0, exc, code=exc.remote_code)
        with self._session_factory.begin() as session:
            state = _state(session)
            reopened = 0
            if remote.acked_through < state.central_acked_through:
                logger.warning(
                    "Le central ne connaît que %s événements sur %s : renvoi.",
                    remote.acked_through,
                    state.central_acked_through,
                )
                reopened = _reopen(session, from_seq=remote.acked_through + 1, to_seq=None)
            self._record_contact(state, remote.server_time, started, remote.acked_through)
            self._clear_failures(state)
        return reopened

    # --- Écritures d'état (transactions courtes) ------------------------------------

    def _apply_response(
        self, batch: Sequence[EventEnvelope], response: PushResponse, started: datetime
    ) -> tuple[int, int]:
        """Enregistre l'accusé : renvoie (nombre d'acquittés, nombre de renvois programmés)."""
        with self._session_factory.begin() as session:
            now = self._clock.now()
            # Événements que cet accusé confirme. Le central peut en confirmer au-delà du
            # lot (déjà reçus lors d'un envoi dont la réponse s'était perdue) : on les
            # prend tous, pour que leurs données passent bien à « synchronisé ».
            newly_acked = session.execute(
                select(OutboxEvent.site_seq, OutboxEvent.entity_type, OutboxEvent.entity_id).where(
                    OutboxEvent.site_seq <= response.acked_through,
                    OutboxEvent.status.in_(_UNACKED),
                )
            ).all()
            if newly_acked:
                session.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.site_seq.in_([row.site_seq for row in newly_acked]))
                    .values(
                        status=OUTBOX_ACKED,
                        acked_at=now,
                        last_error_code=None,
                        last_error_message=None,
                    ),
                    execution_options=_NO_SYNC,
                )
                _refresh_entities(session, [(r.entity_type, r.entity_id) for r in newly_acked])
            acked_rows = len(newly_acked)
            remaining = [e.site_seq for e in batch if e.site_seq > response.acked_through]
            if remaining:
                session.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.site_seq.in_(remaining))
                    .values(attempts=OutboxEvent.attempts + 1, last_attempt_at=now),
                    execution_options=_NO_SYNC,
                )
            rejected = response.rejected
            if rejected is not None:
                session.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.site_seq == rejected.site_seq)
                    .values(
                        status=OUTBOX_REJECTED,
                        last_error_code=rejected.code,
                        last_error_message=rejected.message,
                    ),
                    execution_options=_NO_SYNC,
                )
                # Toute la transaction d'origine est bloquée : ses données sont en erreur
                # (par exemple la note, même si c'est sa ligne d'audit qui est refusée).
                blocked_tx = {e.tx_id for e in batch if e.site_seq == rejected.site_seq}
                _refresh_entities(
                    session,
                    [(e.entity_type, e.entity_id) for e in batch if e.tx_id in blocked_tx],
                    status=SYNC_ERROR,
                )
            reopened = 0
            if response.status is PushStatus.GAP and batch:
                reopened = _reopen(
                    session, from_seq=response.expected_next, to_seq=batch[0].site_seq - 1
                )
                expected = batch[0].site_seq - response.expected_next
                if reopened != expected:
                    reopened = 0  # des événements manquent sur le site : intervention requise

            state = _state(session)
            self._record_contact(state, response.server_time, started, response.acked_through)
            if rejected is None:
                self._clear_failures(state)
            else:
                # Refus : le central répond, mais l'envoi reste bloqué. Les échecs
                # continuent de s'accumuler pour espacer les nouvelles tentatives.
                self._mark_failure(state, rejected.code, rejected.message, offline=False)
        return acked_rows, reopened

    def _record_contact(
        self, state: SyncStateRow, server_time: datetime, started: datetime, acked_through: int
    ) -> None:
        """Le central a répondu : liaison rétablie, décalage d'horloge mesuré."""
        now = self._clock.now()
        midpoint = started + (now - started) / 2
        state.last_attempt_at = now
        state.last_success_at = now
        state.offline_since = None
        state.central_acked_through = acked_through
        state.last_server_time = server_time
        state.clock_offset_ms = (server_time - midpoint) // timedelta(milliseconds=1)

    @staticmethod
    def _clear_failures(state: SyncStateRow) -> None:
        state.consecutive_failures = 0
        state.next_attempt_at = None
        state.last_error_code = None
        state.last_error_message = None

    def _record_failure(
        self, batch: Iterable[EventEnvelope], code: str, message: str, *, offline: bool
    ) -> None:
        seqs = [e.site_seq for e in batch]
        with self._session_factory.begin() as session:
            now = self._clock.now()
            if seqs:
                session.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.site_seq.in_(seqs))
                    .values(
                        attempts=OutboxEvent.attempts + 1,
                        last_attempt_at=now,
                        last_error_code=code,
                        last_error_message=message,
                    ),
                    execution_options=_NO_SYNC,
                )
            state = _state(session)
            state.last_attempt_at = now
            self._mark_failure(state, code, message, offline=offline)
        log = logger.info if offline else logger.warning
        log("Synchronisation : %s (%s)", message, code)

    def _mark_failure(self, state: SyncStateRow, code: str, message: str, *, offline: bool) -> None:
        now = self._clock.now()
        state.consecutive_failures += 1
        if offline and state.offline_since is None:
            state.offline_since = now
        state.next_attempt_at = now + self.backoff(state.consecutive_failures)
        state.last_error_code = code
        state.last_error_message = message

    def backoff(self, failures: int) -> timedelta:
        """Attente avant la tentative suivante : double à chaque échec, plafonnée, ±20 %."""
        exponent = min(max(failures, 1) - 1, 30)
        delay_ms = min(self.settings.backoff_max_ms, self.settings.backoff_base_ms * 2**exponent)
        return timedelta(milliseconds=delay_ms * self._rng.randint(80, 120) // 100)


def _state(session: Session) -> SyncStateRow:
    state = session.get(SyncStateRow, 1)
    if state is None:  # pragma: no cover - créé par la migration s0003
        raise RuntimeError("Ligne sync_state absente : migrations du site incomplètes.")
    return state


def _count_unacked(session: Session) -> int:
    count = session.scalar(
        select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status.in_(_UNACKED))
    )
    return int(count or 0)


def _reopen(session: Session, *, from_seq: int, to_seq: int | None) -> int:
    """Remet « à envoyer » des événements déjà acquittés que le central n'a plus."""
    condition = [OutboxEvent.site_seq >= from_seq, OutboxEvent.status == OUTBOX_ACKED]
    if to_seq is not None:
        condition.append(OutboxEvent.site_seq <= to_seq)
    entities = [
        (t, i)
        for t, i in session.execute(
            select(OutboxEvent.entity_type, OutboxEvent.entity_id).where(*condition)
        )
    ]
    count = cast(
        CursorResult[Any],
        session.execute(
            update(OutboxEvent).where(*condition).values(status=OUTBOX_PENDING, acked_at=None),
            execution_options=_NO_SYNC,
        ),
    ).rowcount
    _refresh_entities(session, entities, status=SYNC_PENDING)
    return count


def _refresh_entities(
    session: Session, pairs: Iterable[tuple[str, UUID]], *, status: str = SYNC_SYNCED
) -> None:
    """Met à jour ``sync_status`` des données métier concernées.

    « synced » n'est posé que si **tous** les événements de la donnée sont acquittés.
    """
    by_type: dict[str, set[UUID]] = {}
    for entity_type, entity_id in pairs:
        if entity_type in SYNCABLE_ENTITIES:
            by_type.setdefault(entity_type, set()).add(entity_id)
    for entity_type, ids in by_type.items():
        model: Any = SYNCABLE_ENTITIES[entity_type]
        stmt = update(model).where(model.id.in_(ids))
        if status == SYNC_SYNCED:
            unacked = exists().where(
                OutboxEvent.entity_type == entity_type,
                OutboxEvent.entity_id == model.id,
                OutboxEvent.status != OUTBOX_ACKED,
            )
            stmt = stmt.where(~unacked)
        session.execute(stmt.values(sync_status=status), execution_options=_NO_SYNC)
