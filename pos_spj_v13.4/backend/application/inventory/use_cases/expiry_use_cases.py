"""Expiry management use cases (§9.4 / §20).

Two application flows over the pure domain ``ExpiryRiskService``:

* ``GenerateExpiryAlertsUseCase`` — scan every AVAILABLE lot with stock, classify
  its expiry risk and enqueue INVENTORY_LOT_EXPIRING / INVENTORY_LOT_EXPIRED
  alerts (read + outbox only; it never moves stock).
* ``ExpireInventoryUseCase`` — for lots already past their expiration, MOVE their
  available stock AVAILABLE → EXPIRED (a status transfer, on-hand unchanged) so
  availability excludes them; disposal (write-off) stays a separate WASTE flow.

Thresholds come from configuration (§56); dates and quantities are Decimal/ISO.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.movement_posting import post_movement
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import ExpiryRisk, InventoryStatus, MovementType
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.domain.inventory.services.expiry_risk_service import ExpiryRiskService
from backend.infrastructure.db.repositories.inventory.base import to_decimal
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)

_ALERT_EVENT = {
    ExpiryRisk.WARNING: InventoryEvents.INVENTORY_LOT_EXPIRING,
    ExpiryRisk.CRITICAL: InventoryEvents.INVENTORY_LOT_EXPIRING,
    ExpiryRisk.EXPIRED: InventoryEvents.INVENTORY_LOT_EXPIRED,
}


@dataclass(frozen=True, slots=True)
class ExpiryAlert:
    lot_id: str
    product_id: str
    branch_id: str
    warehouse_id: str
    risk: ExpiryRisk
    days_to_expiry: int | None
    quantity: str


class GenerateExpiryAlertsUseCase:
    """Classify every AVAILABLE lot's expiry risk and enqueue alerts (§9.4)."""

    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()
        self._risk = ExpiryRiskService()

    def execute(self, connection, *, operation_id: str, actor_user_id: str,
                as_of: date | None = None, warning_days: int = 7,
                critical_days: int = 2) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.LOT_VIEW)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        alerts: list[ExpiryAlert] = []
        try:
            with InventoryUnitOfWork(connection) as uow:
                for i, row in enumerate(uow.lots.list_available_balances_with_expiry()):
                    assessment = self._risk.classify(
                        row["expiration_date"], as_of=as_of,
                        warning_days=warning_days, critical_days=critical_days)
                    event = _ALERT_EVENT.get(assessment.risk)
                    if event is None:            # OK — no alert
                        continue
                    alerts.append(ExpiryAlert(
                        lot_id=row["lot_id"], product_id=row["product_id"],
                        branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
                        risk=assessment.risk, days_to_expiry=assessment.days_to_expiry,
                        quantity=str(to_decimal(row["quantity"]))))
                    payload = build_event_payload(
                        event, operation_id=f"{operation_id}:{i}", entity_id=row["lot_id"],
                        product_id=row["product_id"], lot_id=row["lot_id"],
                        branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
                        user_id=actor_user_id, risk=assessment.risk.value,
                        days_to_expiry=assessment.days_to_expiry)
                    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event,
                                       payload_json=json.dumps(payload),
                                       operation_id=f"{operation_id}:{i}")
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok(f"{len(alerts)} alertas de caducidad",
                                  operation_id=operation_id, alerts=alerts)


class ExpireInventoryUseCase:
    """Move expired lots' available stock to the EXPIRED bucket (§9.4).

    A status transfer AVAILABLE → EXPIRED: on-hand is unchanged and the stock is
    still traceable, but it no longer counts toward available-to-promise. Physical
    disposal is a separate WASTE write-off. Atomic in one UoW; idempotent per
    balance via the derived operation_id.
    """

    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()
        self._risk = ExpiryRiskService()

    def execute(self, connection, *, operation_id: str, actor_user_id: str,
                as_of: date | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.LOT_BLOCK)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        expired_lots: set[str] = set()
        moved = 0
        try:
            with InventoryUnitOfWork(connection) as uow:
                for row in uow.lots.list_available_balances_with_expiry():
                    assessment = self._risk.classify(row["expiration_date"], as_of=as_of)
                    if assessment.risk is not ExpiryRisk.EXPIRED:
                        continue
                    qty = to_decimal(row["quantity"])
                    wgt = to_decimal(row["weight"])
                    if qty == 0 and wgt == 0:
                        continue
                    loc = row["location_id"] or row["warehouse_id"]
                    line = InventoryMovementLine.create(
                        product_id=row["product_id"], quantity=qty, weight=wgt,
                        lot_id=row["lot_id"], from_location_id=loc, to_location_id=loc,
                        from_status=InventoryStatus.AVAILABLE,
                        to_status=InventoryStatus.EXPIRED, reason_code="EXPIRY")
                    movement = InventoryMovement.create(
                        movement_type=MovementType.EXPIRY_STATUS_TRANSFER,
                        branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
                        source_module="inventory", source_document_type="EXPIRY",
                        source_document_id=row["lot_id"],
                        operation_id=f"{operation_id}:{row['balance_id']}",
                        created_by_user_id=actor_user_id, lines=[line])
                    _, already = post_movement(uow, movement, actor_user_id=actor_user_id)
                    if already:
                        continue
                    moved += 1
                    if row["lot_id"] not in expired_lots:
                        expired_lots.add(row["lot_id"])
                        payload = build_event_payload(
                            InventoryEvents.INVENTORY_LOT_EXPIRED,
                            operation_id=f"{operation_id}:{row['lot_id']}",
                            entity_id=row["lot_id"], product_id=row["product_id"],
                            lot_id=row["lot_id"], branch_id=row["branch_id"],
                            warehouse_id=row["warehouse_id"], user_id=actor_user_id)
                        uow.outbox.enqueue(
                            event_id=payload["event_id"],
                            event_name=InventoryEvents.INVENTORY_LOT_EXPIRED,
                            payload_json=json.dumps(payload),
                            operation_id=f"{operation_id}:{row['lot_id']}")
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok(
            f"{moved} balances caducados ({len(expired_lots)} lotes)",
            operation_id=operation_id, moved=moved, expired_lots=len(expired_lots))
