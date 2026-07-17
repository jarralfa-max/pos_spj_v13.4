"""Purchase-order use cases (§59, §36) — the enterprise supply route.

Create → submit → approve → send → acknowledge → receive (partial/total). A
sensitive change after approval bumps the version and re-opens approval, keeping
the prior snapshot. Receiving generates a goods receipt and enters ONLY the
accepted quantity into inventory (via a post-commit event). Every transition
re-validates its granular permission, is atomic, and is audited.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.entities import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    ReceiptDiscrepancy,
)
from backend.domain.procurement.enums import (
    DiscrepancyType,
    PurchaseOrderStatus,
    PurchaseType,
)
from backend.domain.procurement.events import ProcurementEvents, build_event_payload
from backend.domain.procurement.exceptions import (
    ProcurementDomainError,
    PurchasePermissionDeniedError,
)
from backend.domain.procurement.policies import SegregationOfDutiesPolicy
from backend.domain.procurement.receiving_matching_policies import ReceiptTolerancePolicy
from backend.domain.procurement.value_objects import Money, Tolerance
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


def _year() -> int:
    from datetime import date
    return date.today().year


def _emit(uow, event_name, *, document_id, operation_id, actor_user_id=None, **extra):
    payload = build_event_payload(event_name, operation_id=operation_id,
                                  document_id=document_id, user_id=actor_user_id, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


class CreatePurchaseOrderUseCase:
    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str, supplier_id: str,
                branch_id: str, warehouse_id: str, lines: list[dict],
                purchase_type: str = PurchaseType.INVENTORY.value, currency_code: str = "MXN",
                requisition_id: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.ORDER_CREATE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            existing = uow.orders.get_by_operation(operation_id)
            if existing is not None:
                return ProcurementResult.ok("Orden ya registrada", entity_id=existing.id,
                                            operation_id=operation_id,
                                            status=existing.status.value)
            try:
                po = PurchaseOrder.create(
                    uow.sequences.next_number("OC", _year()), supplier_id, branch_id,
                    warehouse_id, created_by_user_id=actor_user_id,
                    purchase_type=PurchaseType(purchase_type), currency_code=currency_code)
                for raw in lines:
                    po.lines.append(PurchaseOrderLine.create(
                        raw["product_id"], raw.get("description", ""), str(raw["quantity"]),
                        Money(str(raw["unit_price"]), currency_code),
                        conversion_factor=Decimal(str(raw.get("conversion_factor", "1"))),
                        destination_warehouse_id=raw.get("destination_warehouse_id")))
                if not po.lines:
                    return ProcurementResult.fail("La orden requiere al menos una línea",
                                                  "EMPTY", operation_id=operation_id)
            except (ProcurementDomainError, ValueError) as exc:
                return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.orders.save(po)
            uow.orders.set_operation_id(po.id, operation_id)
            uow.orders.record_version(po, before=None, reason="alta", changed_by_user_id=actor_user_id)
            uow.audit.record(action=ProcurementEvents.PURCHASE_ORDER_CREATED,
                             actor_user_id=actor_user_id, document_id=po.id,
                             reason="alta orden", operation_id=operation_id, branch_id=branch_id)
            _emit(uow, ProcurementEvents.PURCHASE_ORDER_CREATED, document_id=po.id,
                  operation_id=operation_id, actor_user_id=actor_user_id, supplier_id=supplier_id,
                  branch_id=branch_id, document_number=po.document_number,
                  total=str(po.total().amount))
        return ProcurementResult.ok("Orden creada", entity_id=po.id, operation_id=operation_id,
                                    status=po.status.value, document_number=po.document_number,
                                    total=str(po.total().amount))


class ApprovePurchaseOrderUseCase:
    """Submit (if draft) + approve. Creator ≠ approver (segregation of duties)."""

    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._sod = SegregationOfDutiesPolicy()

    def execute(self, connection, *, approver_user_id: str, purchase_order_id: str,
                operation_id: str, reason: str = "") -> ProcurementResult:
        try:
            self._auth.require(approver_user_id, PurchasePermissions.ORDER_APPROVE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            po = uow.orders.get(purchase_order_id)
            if po is None:
                return ProcurementResult.fail("Orden inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            try:
                self._sod.enforce_distinct(
                    po.created_by_user_id, approver_user_id,
                    "quien crea la orden no la aprueba")
                if po.status is PurchaseOrderStatus.DRAFT:
                    po.submit()
                po.approve(approver_user_id)
            except ProcurementDomainError as exc:
                code = "SEGREGATION" if "Separación" in str(exc) else "INVALID_STATE"
                return ProcurementResult.fail(str(exc), code, operation_id=operation_id)
            uow.orders.save(po)
            uow.audit.record(action=ProcurementEvents.PURCHASE_ORDER_APPROVED,
                             actor_user_id=approver_user_id, authorized_by=approver_user_id,
                             document_id=po.id, reason=reason, operation_id=operation_id)
            _emit(uow, ProcurementEvents.PURCHASE_ORDER_APPROVED, document_id=po.id,
                  operation_id=operation_id, actor_user_id=approver_user_id,
                  authorized_by=approver_user_id, version=po.version)
        return ProcurementResult.ok("Orden aprobada", entity_id=po.id,
                                    operation_id=operation_id, status=po.status.value)


class SendPurchaseOrderUseCase:
    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, purchase_order_id: str,
                operation_id: str, acknowledge: bool = False) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.ORDER_SEND)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            po = uow.orders.get(purchase_order_id)
            if po is None:
                return ProcurementResult.fail("Orden inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            try:
                po.send()
                if acknowledge:
                    po.acknowledge()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            uow.orders.save(po)
            event = (ProcurementEvents.PURCHASE_ORDER_ACKNOWLEDGED if acknowledge
                     else ProcurementEvents.PURCHASE_ORDER_SENT)
            uow.audit.record(action=event, actor_user_id=actor_user_id, document_id=po.id,
                             operation_id=operation_id)
            _emit(uow, event, document_id=po.id, operation_id=operation_id,
                  actor_user_id=actor_user_id, supplier_id=po.supplier_id)
        return ProcurementResult.ok("Orden enviada", entity_id=po.id,
                                    operation_id=operation_id, status=po.status.value)


class ChangePurchaseOrderUseCase:
    """A sensitive change after approval bumps the version and re-opens approval,
    keeping the prior snapshot (§36)."""

    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, purchase_order_id: str,
                operation_id: str, reason: str, line_changes: list[dict] | None = None
                ) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.ORDER_CHANGE_APPROVED)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        if not reason or not reason.strip():
            return ProcurementResult.fail("El cambio requiere un motivo", "VALIDATION",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            po = uow.orders.get(purchase_order_id)
            if po is None:
                return ProcurementResult.fail("Orden inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            before = uow.orders.snapshot(po)
            try:
                if line_changes:
                    _apply_line_changes(po, line_changes)
                po.create_new_version(reason.strip())
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            uow.orders.save(po)
            uow.orders.record_version(po, before=before, reason=reason.strip(),
                                      changed_by_user_id=actor_user_id)
            uow.audit.record(action=ProcurementEvents.PURCHASE_ORDER_CHANGED,
                             actor_user_id=actor_user_id, document_id=po.id,
                             reason=reason.strip(), operation_id=operation_id,
                             before_json=json.dumps(before))
            _emit(uow, ProcurementEvents.PURCHASE_ORDER_CHANGED, document_id=po.id,
                  operation_id=operation_id, actor_user_id=actor_user_id, version=po.version)
        return ProcurementResult.ok("Orden versionada; requiere reaprobación", entity_id=po.id,
                                    operation_id=operation_id, status=po.status.value,
                                    version=po.version)


class ReceivePurchaseOrderUseCase:
    """Registers a goods receipt against an order. Only the accepted quantity enters
    inventory; over-tolerance receipts need an override permission; the receiver
    cannot also be the price changer (segregation)."""

    def __init__(self, authorization=None, *, tolerance: Tolerance | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._tolerance = tolerance or Tolerance(Decimal("0"))
        self._tol_policy = ReceiptTolerancePolicy()
        self._sod = SegregationOfDutiesPolicy()

    def execute(self, connection, *, actor_user_id: str, purchase_order_id: str,
                operation_id: str, receipt_lines: list[dict],
                price_changer_id: str | None = None,
                has_over_receive_permission: bool = False) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RECEIPT_COMPLETE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            po = uow.orders.get(purchase_order_id)
            if po is None:
                return ProcurementResult.fail("Orden inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            lines_by_product = {ln.product_id: ln for ln in po.lines}
            try:
                if price_changer_id:
                    self._sod.enforce_receiver_not_price_changer(actor_user_id, price_changer_id)
                gr = GoodsReceipt.create(
                    uow.sequences.next_number("REC", _year()), po.supplier_id, po.branch_id,
                    po.warehouse_id, received_by_user_id=actor_user_id,
                    purchase_order_id=po.id)
                received_by_line: dict[str, Decimal] = {}
                for raw in receipt_lines:
                    product_id = raw["product_id"]
                    po_line = lines_by_product.get(product_id)
                    ordered = po_line.ordered_quantity if po_line else Decimal("0")
                    received = Decimal(str(raw["received_quantity"]))
                    accepted = Decimal(str(raw.get("accepted_quantity", raw["received_quantity"])))
                    self._tol_policy.enforce_over_receipt(
                        ordered, received, self._tolerance,
                        has_override_permission=has_over_receive_permission)
                    gr.add_line(GoodsReceiptLine.create(product_id, ordered, received, accepted))
                    if raw.get("discrepancy_type"):
                        gr.add_discrepancy(ReceiptDiscrepancy.create(
                            DiscrepancyType(raw["discrepancy_type"]), ordered, received,
                            raw.get("discrepancy_reason", "")))
                    if po_line is not None:
                        received_by_line[po_line.id] = received
                gr.complete()
                po.register_receipt(received_by_line)
            except ProcurementDomainError as exc:
                code = ("SEGREGATION" if "Separación" in str(exc)
                        else "OVER_TOLERANCE" if "tolerancia" in str(exc).lower()
                        else "INVALID_STATE")
                return ProcurementResult.fail(str(exc), code, operation_id=operation_id)
            uow.receipts.save(gr)
            uow.orders.save(po)
            uow.audit.record(action=ProcurementEvents.GOODS_RECEIPT_COMPLETED,
                             actor_user_id=actor_user_id, document_id=gr.id,
                             operation_id=operation_id, branch_id=po.branch_id)
            _emit(uow, ProcurementEvents.GOODS_RECEIPT_COMPLETED, document_id=gr.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  supplier_id=po.supplier_id, branch_id=po.branch_id,
                  purchase_order_id=po.id, warehouse_id=po.warehouse_id,
                  inventory_lines=[{"product_id": ln.product_id,
                                    "quantity": str(ln.inventory_quantity())}
                                   for ln in gr.lines])
            if gr.discrepancies:
                _emit(uow, ProcurementEvents.GOODS_RECEIPT_DISCREPANCY, document_id=gr.id,
                      operation_id=operation_id, actor_user_id=actor_user_id,
                      count=len(gr.discrepancies))
        return ProcurementResult.ok("Recepción registrada", entity_id=gr.id,
                                    operation_id=operation_id,
                                    order_status=po.status.value,
                                    accepted=str(gr.total_accepted()))


# ── helpers ─────────────────────────────────────────────────────────────────
def _apply_line_changes(po: PurchaseOrder, line_changes: list[dict]) -> None:
    by_id = {ln.id: ln for ln in po.lines}
    for change in line_changes:
        line = by_id.get(change.get("line_id"))
        if line is None:
            continue
        if "unit_price" in change:
            line.unit_price = Money(str(change["unit_price"]), line.unit_price.currency_code)
        if "ordered_quantity" in change:
            line.ordered_quantity = Decimal(str(change["ordered_quantity"]))
