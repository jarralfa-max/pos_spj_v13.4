"""ExpiryQueryService — the read the Caducidades UI consults (§9.4 / §20).

Read-only: joins available balances to their lot's expiration and classifies each
with the pure ``ExpiryRiskService`` (EXPIRED / CRITICAL / WARNING / OK), returning
only the at-risk lots sorted by nearest expiry. It never emits events or moves
stock — that is the expiry use cases' job (GenerateExpiryAlerts / ExpireInventory).
"""

from __future__ import annotations

from datetime import date

from backend.domain.inventory.enums import ExpiryRisk
from backend.domain.inventory.services.expiry_risk_service import ExpiryRiskService
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
    zn,
)

_AT_RISK = (ExpiryRisk.EXPIRED, ExpiryRisk.CRITICAL, ExpiryRisk.WARNING)


class ExpiryQueryService(InventoryRepositoryBase):
    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._risk = ExpiryRiskService()

    def list_at_risk(self, *, branch_id: str | None = None, as_of: date | None = None,
                     warning_days: int = 7, critical_days: int = 2) -> list[dict]:
        """At-risk AVAILABLE lots (expired/critical/warning), nearest expiry first.
        Rows carry product, lot, quantity, risk and days-to-expiry for display."""
        sql = ("SELECT b.product_id, b.branch_id, b.lot_id, b.quantity,"
               " l.lot_code, l.expiration_date FROM inventory_balances b"
               " JOIN inventory_lots l ON l.id = b.lot_id"
               " WHERE b.inventory_status='AVAILABLE' AND b.lot_id IS NOT NULL"
               " AND b.lot_id<>''")
        params: tuple = ()
        if branch_id:
            sql += " AND b.branch_id=?"
            params += (branch_id,)
        sql += " ORDER BY l.expiration_date, b.lot_id"
        out = []
        for r in self._query(sql, params):
            assessment = self._risk.classify(
                r["expiration_date"], as_of=as_of,
                warning_days=warning_days, critical_days=critical_days)
            if assessment.risk not in _AT_RISK:
                continue
            out.append({
                "product_id": r["product_id"], "lot_id": r["lot_id"],
                "lot_code": r["lot_code"], "quantity": to_decimal(r["quantity"]),
                "expiration_date": zn(r["expiration_date"]),
                "risk": assessment.risk.value,
                "days_to_expiry": assessment.days_to_expiry,
            })
        return out
