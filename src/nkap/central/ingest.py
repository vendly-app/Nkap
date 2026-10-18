"""Réception d'un lot d'événements d'un site (cœur de la synchronisation, décision 008).

Règles appliquées, dans cet ordre, pour chaque transaction d'origine du site :

1. **Doublon** : si ses événements sont déjà connus (même ``event_id`` et même contenu),
   on l'ignore. Un même lot envoyé deux fois ne produit donc qu'un seul effet.
2. **Ordre** : elle doit commencer exactement au numéro attendu (dernier numéro reçu + 1).
   Sinon : trou (``gap``, le site doit renvoyer les événements manquants) ou conflit
   (numéro déjà utilisé par un autre événement).
3. **Complétude** : tous les événements de la transaction doivent être présents.
4. **Application** tout-ou-rien : chaque événement est vérifié puis appliqué ; au moindre
   refus, rien de cette transaction n'est conservé et l'envoi s'arrête là.

Les transactions précédentes du lot restent acquises : l'accusé ``acked_through`` dit
exactement jusqu'où le central a tout enregistré.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from nkap.central.auth import AuthenticatedSite
from nkap.central.handlers import ApplyContext, Handler
from nkap.central.models import InboxEvent, SyncSiteState
from nkap.core.canonical import canonical_json
from nkap.core.clock import Clock
from nkap.core.errors import NkapError
from nkap.events.envelope import EventEnvelope
from nkap.events.registry import EventRegistry, UnknownEventError
from nkap.sync.protocol import PushRequest, PushResponse, PushStatus, RejectedEvent


class SiteMismatchError(NkapError):
    """Événement au nom d'un autre site ou d'une autre société que le site authentifié."""

    default_code = "auth.site_mismatch"
    http_status = 403


class InvalidBatchError(NkapError):
    """Lot mal formé (événements non triés ou en double)."""

    default_code = "sync.batch_not_ordered"
    http_status = 422


@dataclass(frozen=True, slots=True)
class _Stop:
    status: PushStatus
    rejected: RejectedEvent | None = None


def _iter_transactions(events: Sequence[EventEnvelope]) -> Iterator[list[EventEnvelope]]:
    """Regroupe les événements consécutifs d'une même transaction d'origine."""
    group: list[EventEnvelope] = []
    for event in events:
        if group and event.tx_id != group[0].tx_id:
            yield group
            group = []
        group.append(event)
    if group:
        yield group


def _rejection(event: EventEnvelope, status: PushStatus, error: NkapError) -> _Stop:
    return _Stop(
        status,
        RejectedEvent(
            event_id=event.event_id,
            site_seq=event.site_seq,
            code=error.code,
            message=error.message(),
        ),
    )


class SyncIngestor:
    """Applique les lots reçus des sites sur la base centrale."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        clock: Clock,
        registry: EventRegistry,
        handlers: Mapping[str, Handler],
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock
        self.registry = registry
        self.handlers = handlers

    def ingest(self, site: AuthenticatedSite, request: PushRequest) -> PushResponse:
        self._check_batch(site, request)
        with self.session_factory.begin() as session:
            # Verrou sur l'état du site : deux envois simultanés du même site
            # sont traités l'un après l'autre.
            state = session.execute(
                select(SyncSiteState).where(SyncSiteState.site_id == site.site_id).with_for_update()
            ).scalar_one()
            now = self.clock.now()
            stop: _Stop | None = None
            for group in _iter_transactions(request.events):
                stop = self._apply_transaction(session, site, state, group)
                if stop is not None:
                    break
            state.last_received_at = now
            acked = state.last_seq
        status = stop.status if stop else PushStatus.OK
        return PushResponse(
            status=status,
            acked_through=acked,
            expected_next=acked + 1,
            server_time=now,
            rejected=stop.rejected if stop else None,
        )

    @staticmethod
    def _check_batch(site: AuthenticatedSite, request: PushRequest) -> None:
        if request.site_id != site.site_id:
            raise SiteMismatchError()
        previous = 0
        for event in request.events:
            if event.site_id != site.site_id or event.company_id != site.company_id:
                raise SiteMismatchError()
            if event.site_seq <= previous:
                raise InvalidBatchError()
            previous = event.site_seq

    def _apply_transaction(
        self,
        session: Session,
        site: AuthenticatedSite,
        state: SyncSiteState,
        group: list[EventEnvelope],
    ) -> _Stop | None:
        first = group[0]

        # 1. Doublon ?
        known = {
            row.event_id: row
            for row in session.scalars(
                select(InboxEvent).where(InboxEvent.event_id.in_([e.event_id for e in group]))
            )
        }
        if known:
            for event in group:
                row = known.get(event.event_id)
                if (
                    row is None
                    or row.site_seq != event.site_seq
                    or row.fingerprint != event.fingerprint()
                ):
                    error = NkapError("sync.event_mismatch", event_id=event.event_id)
                    return _rejection(event, PushStatus.CONFLICT, error)
            return None

        # 2. Ordre.
        expected = state.last_seq + 1
        if first.site_seq < expected:
            error = NkapError("sync.seq_conflict", site_seq=first.site_seq)
            return _rejection(first, PushStatus.CONFLICT, error)
        if first.site_seq > expected:
            return _Stop(PushStatus.GAP)

        # 3. Complétude de la transaction d'origine.
        seqs = [e.site_seq for e in group]
        complete = (
            len(group) == first.tx_size
            and all(e.tx_size == first.tx_size for e in group)
            and seqs == list(range(first.site_seq, first.site_seq + len(group)))
        )
        if not complete:
            error = NkapError("sync.incomplete_tx", site_seq=first.site_seq)
            return _rejection(first, PushStatus.REJECTED, error)

        # 4. Application tout-ou-rien (point de sauvegarde).
        ctx = ApplyContext(
            now=self.clock.now(),
            site=site,
            audit_last_seq=state.audit_last_seq,
            audit_last_hash=state.audit_last_hash,
        )
        current = first
        try:
            with session.begin_nested():
                for event in group:
                    current = event
                    payload = self.registry.parse_payload(event)
                    handler = self.handlers.get(event.event_type)
                    if handler is None:
                        raise UnknownEventError(
                            event_type=event.event_type, payload_version=event.payload_version
                        )
                    handler(session, event, payload, ctx)
                    session.add(_inbox_row(event, ctx))
                session.flush()
        except NkapError as error:
            return _rejection(current, PushStatus.REJECTED, error)
        except IntegrityError:
            # Contrainte de la base violée : on bloque proprement sur cet événement
            # (visible côté site) plutôt que de faire échouer tout l'envoi.
            integrity = NkapError("sync.integrity_error", site_seq=current.site_seq)
            return _rejection(current, PushStatus.REJECTED, integrity)

        state.last_seq = group[-1].site_seq
        state.audit_last_seq = ctx.audit_last_seq
        state.audit_last_hash = ctx.audit_last_hash
        return None


def _inbox_row(event: EventEnvelope, ctx: ApplyContext) -> InboxEvent:
    return InboxEvent(
        event_id=event.event_id,
        site_id=event.site_id,
        site_seq=event.site_seq,
        tx_id=event.tx_id,
        tx_size=event.tx_size,
        event_type=event.event_type,
        payload_version=event.payload_version,
        company_id=event.company_id,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        entity_version=event.entity_version,
        occurred_at=event.occurred_at,
        business_date=event.business_date,
        created_by=event.created_by,
        payload=canonical_json(event.payload),
        fingerprint=event.fingerprint(),
        received_at=ctx.now,
    )
