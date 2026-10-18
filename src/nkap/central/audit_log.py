"""Journal d'audit des actions effectuées au central."""

from __future__ import annotations

from nkap.audit.store import AuditStore
from nkap.central.models import CentralAuditChainHead, CentralAuditLog

CENTRAL_AUDIT = AuditStore(CentralAuditLog, CentralAuditChainHead)
