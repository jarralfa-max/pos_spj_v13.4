"""Fidelidad/Loyalty audit trail writer (master prompt §61).

Deliberately reuses the existing app-wide `core.services.auto_audit.audit_write`
sink (backed by `container.audit_service`/the `audit_logs` table) instead of
standing up a parallel `loyalty_audit_log` table — mirrors
``backend/application/sales/audit.py``'s own reasoning (one canonical
persistence route per functional area, master prompt §3/§64).
"""

from __future__ import annotations

import json

from backend.domain.loyalty.value_objects.loyalty_audit_entry import LoyaltyAuditEntry


def record_loyalty_audit_entry(container, entry: LoyaltyAuditEntry) -> None:
    """Persist a `LoyaltyAuditEntry` via the canonical `audit_write` sink."""
    from core.services.auto_audit import audit_write

    extra = {
        "operation_id": entry.operation_id,
        "authorized_by": entry.authorized_by,
        "reason": entry.reason,
        "device_id": entry.device_id,
        "occurred_at": entry.occurred_at,
    }
    detalles = json.dumps({k: v for k, v in extra.items() if v is not None},
                           ensure_ascii=False)

    audit_write(
        container,
        modulo="GROWTH_ENGINE",
        accion=entry.action,
        entidad="fidelidad",
        entidad_id=entry.entity_id or "",
        usuario=entry.user_id,
        detalles=detalles,
        before=dict(entry.before),
        after=dict(entry.after),
        sucursal_id=entry.branch_id,
    )
