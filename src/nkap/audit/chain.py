"""Calcul et vérification de la chaîne d'empreintes du journal d'audit."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from nkap.core.canonical import canonical_json, sha256_hex

GENESIS_HASH = "0" * 64
"""Empreinte « précédente » de la toute première ligne d'un journal."""


def normalize_details(details: Mapping[str, object] | None) -> dict[str, Any]:
    """Détails ramenés à du JSON simple (textes, entiers...), comme une fois relus en base."""
    loaded = json.loads(canonical_json(dict(details or {})))
    if not isinstance(loaded, dict):  # pragma: no cover - impossible avec un Mapping
        raise TypeError("Les détails d'audit doivent former un objet JSON.")
    return loaded


@dataclass(frozen=True, slots=True)
class AuditContent:
    """Contenu d'une ligne du journal, tel qu'il est couvert par l'empreinte."""

    chain_seq: int
    audit_id: UUID
    occurred_at: datetime
    site_id: UUID | None
    actor_id: UUID | None
    actor_label: str
    action: str
    entity_type: str | None
    entity_id: UUID | None
    details: dict[str, Any]
    prev_hash: str

    def compute_hash(self) -> str:
        return sha256_hex(
            canonical_json(
                {
                    "chain_seq": self.chain_seq,
                    "audit_id": self.audit_id,
                    "occurred_at": self.occurred_at,
                    "site_id": self.site_id,
                    "actor_id": self.actor_id,
                    "actor_label": self.actor_label,
                    "action": self.action,
                    "entity_type": self.entity_type,
                    "entity_id": self.entity_id,
                    "details": self.details,
                    "prev_hash": self.prev_hash,
                }
            )
        )


@dataclass(frozen=True, slots=True)
class ChainVerification:
    """Résultat d'une vérification de chaîne."""

    ok: bool
    checked: int
    first_broken_seq: int | None = None
    reason: str | None = None


def verify_chain(
    entries: Iterable[tuple[AuditContent, str]],
    *,
    start_seq: int = 1,
    start_prev_hash: str = GENESIS_HASH,
) -> ChainVerification:
    """Vérifie une suite de lignes ``(contenu, empreinte enregistrée)`` dans l'ordre.

    Contrôles : numéros consécutifs, chaînage sur l'empreinte précédente, et empreinte
    recalculée identique à l'empreinte enregistrée.
    """
    expected_seq = start_seq
    expected_prev = start_prev_hash
    checked = 0
    for content, stored_hash in entries:
        if content.chain_seq != expected_seq:
            return ChainVerification(
                False, checked, content.chain_seq, f"numéro attendu {expected_seq}"
            )
        if content.prev_hash != expected_prev:
            return ChainVerification(False, checked, content.chain_seq, "chaînage rompu")
        if content.compute_hash() != stored_hash:
            return ChainVerification(False, checked, content.chain_seq, "ligne modifiée")
        expected_prev = stored_hash
        expected_seq += 1
        checked += 1
    return ChainVerification(True, checked)
