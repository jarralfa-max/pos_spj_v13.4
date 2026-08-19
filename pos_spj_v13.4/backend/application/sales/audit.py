"""Sales/POS audit trail writer (master prompt §63).

Deliberately reuses the existing app-wide `core.services.auto_audit.audit_write`
sink (backed by `container.audit_service`/the `audit_logs` table) instead of
standing up a parallel `sales_audit_log` table — this repo's own rule against
duplicate routes for the same functional area (§3/§64) applies to persistence
just as much as to use cases. `audit_write`'s parameter set is narrower than
the master prompt's `SalesAuditEntry` (no dedicated columns for
`authorized_by`/`operation_id`/`workstation_id`/`device_id`/`reason`) — this
module builds the richer `SalesAuditEntry` value object first (so callers get
real validation and a typed record), then folds the fields `audit_write` has
no column for into its free-text `detalles`, structured as `key=value` pairs
so they stay greppable.

If a future phase needs queryable columns for those fields, extend
`audit_logs` via a migration rather than inventing a second table — flagged
here, not solved, since that's out of SALES-2's scope.
"""

from __future__ import annotations

import json

from backend.domain.sales.value_objects.sales_audit_entry import SalesAuditEntry


def record_sales_audit_entry(container, entry: SalesAuditEntry) -> None:
    """Persist a `SalesAuditEntry` via the canonical `audit_write` sink."""
    from core.services.auto_audit import audit_write

    extra = {
        "operation_id": entry.operation_id,
        "authorized_by": entry.authorized_by,
        "reason": entry.reason,
        "workstation_id": entry.workstation_id,
        "device_id": entry.device_id,
        "occurred_at": entry.occurred_at,
    }
    detalles = json.dumps({k: v for k, v in extra.items() if v is not None},
                           ensure_ascii=False)

    audit_write(
        container,
        modulo="POS",
        accion=entry.action,
        entidad="venta",
        entidad_id=entry.sale_id or "",
        usuario=entry.user_id,
        detalles=detalles,
        before=dict(entry.before),
        after=dict(entry.after),
        sucursal_id=entry.branch_id,
    )
