"""SalesAuditEntry — one auditable Sales/POS action (master prompt §63).

Field set is exactly the one the master prompt names: user_id, authorized_by,
operation_id, sale_id, action, before, after, reason, branch_id,
workstation_id, device_id, occurred_at. `authorized_by`/`sale_id`/`device_id`
are optional — most actions (adding a line, searching a customer) have no
hot-authorization and no device involved; `reason` is optional for the same
reason (only authorization-gated actions require one — enforced by
AuthorizationGrant, not here).

This is a pure value object; persistence is `backend/application/sales/audit.py`
(SALES-2 deliberately reuses the existing app-wide `core.services.auto_audit`
sink rather than standing up a parallel `sales_audit_log` table — see that
module's own docstring for why).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.domain.sales.exceptions import InvalidSalesAuditFieldError


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SalesAuditEntry:
    user_id: str
    operation_id: str
    action: str
    branch_id: str
    authorized_by: str | None = None
    sale_id: str | None = None
    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None
    workstation_id: str | None = None
    device_id: str | None = None
    occurred_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        if not self.user_id:
            raise InvalidSalesAuditFieldError("user_id requerido")
        if not self.operation_id:
            raise InvalidSalesAuditFieldError("operation_id requerido")
        if not self.action:
            raise InvalidSalesAuditFieldError("action requerido")
        if not self.branch_id:
            raise InvalidSalesAuditFieldError("branch_id requerido")
