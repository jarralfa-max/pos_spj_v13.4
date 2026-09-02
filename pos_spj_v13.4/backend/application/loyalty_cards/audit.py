"""Loyalty Cards audit trail writer (master prompt §61).

Deliberately reuses the existing app-wide `core.services.auto_audit.audit_write`
sink instead of standing up a parallel table — same reasoning as
``backend/application/loyalty/audit.py``.
"""

from __future__ import annotations

import json

from backend.domain.loyalty_cards.value_objects.card_audit_entry import CardAuditEntry


def record_card_audit_entry(container, entry: CardAuditEntry) -> None:
    """Persist a `CardAuditEntry` via the canonical `audit_write` sink."""
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
        modulo="TARJETAS_FIDELIDAD",
        accion=entry.action,
        entidad="tarjeta_fidelidad",
        entidad_id=entry.card_id or "",
        usuario=entry.user_id,
        detalles=detalles,
        before=dict(entry.before),
        after=dict(entry.after),
        sucursal_id=entry.branch_id,
    )
