"""QR-container reception (migrated from the legacy monolith to the canonical
bounded context).

A QR reception is a physical receipt of an already-assigned container: the QR
carries the supplier and payment terms. Canonically it is a DirectPurchase with
``source_channel = MOBILE_RECEIVING`` and immediate receipt, which produces a
GoodsReceipt and an inventory-entry event for the received quantity.

Behavior preserved from the legacy `RecepcionQRService.procesar_recepcion`:
- atomic transaction (UoW) across receipt + traceability;
- ONLY the received quantity enters inventory (via event, carrying unit_cost so
  the Inventory context computes the weighted-average cost — its responsibility);
- the pending balance (monto_total − monto_pagado) becomes a supplier payable
  (CxP) via event; a fully-paid container raises no payable;
- the QR container advances to received/available.

New-architecture guarantees: no direct writes to inventory / finance / cash
tables; effects travel as canonical events; idempotent by operation_id and by
the container's own received state.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.entities import (
    DirectPurchase,
    DirectPurchaseLine,
    GoodsReceipt,
    GoodsReceiptLine,
)
from backend.domain.procurement.enums import (
    DirectPurchaseMode,
    PaymentCondition,
    PurchaseType,
    SourceChannel,
)
from backend.domain.procurement.events import ProcurementEvents, build_event_payload
from backend.domain.procurement.exceptions import (
    ProcurementDomainError,
    PurchasePermissionDeniedError,
)
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


def _year() -> int:
    from datetime import date
    return date.today().year


class CompleteQrReceptionUseCase:
    """Completes a QR-container reception as a canonical GoodsReceipt."""

    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def _emit(self, uow, event_name, *, document_id, operation_id, actor_user_id, **extra):
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      document_id=document_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                           payload_json=json.dumps(payload), operation_id=operation_id)

    def execute(self, connection, *, actor_user_id: str, operation_id: str, uuid_qr: str,
                items: list[dict], branch_id: str, warehouse_id: str | None = None,
                notes: str = "", currency_code: str = "MXN") -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RECEIPT_DIRECT)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        warehouse_id = warehouse_id or branch_id
        with ProcurementUnitOfWork(connection) as uow:
            existing = uow.direct_purchases.get_by_operation(operation_id)
            if existing is not None:
                return ProcurementResult.ok("Recepción QR ya registrada",
                                            entity_id=existing.id, operation_id=operation_id,
                                            status=existing.status.value)
            assignment = uow.qr_containers.read_assignment(uuid_qr)
            if assignment is None:
                return ProcurementResult.fail("Contenedor QR sin asignación",
                                              "QR_NOT_FOUND", operation_id=operation_id)
            if uow.qr_containers.is_received(uuid_qr):
                return ProcurementResult.ok("Contenedor QR ya recibido",
                                            operation_id=operation_id, status="RECEIVED")
            if not items:
                return ProcurementResult.fail("La recepción requiere al menos un ítem",
                                              "EMPTY", operation_id=operation_id)

            amount_total = assignment["amount_total"]
            amount_paid = assignment["amount_paid"]
            balance = amount_total - amount_paid
            payment_condition = (PaymentCondition.SUPPLIER_CREDIT if balance > 0
                                 else PaymentCondition.IMMEDIATE_PAYMENT)
            supplier_id = str(assignment["supplier_id"] or "QR-OCCASIONAL")

            try:
                dp = DirectPurchase.create(
                    uow.sequences.next_number("CD", _year()), supplier_id, branch_id,
                    warehouse_id, DirectPurchaseMode.DIRECT_WITH_IMMEDIATE_RECEIPT,
                    payment_condition, created_by_user_id=actor_user_id,
                    currency_code=currency_code,
                    source_channel=SourceChannel.MOBILE_RECEIVING,
                    purchase_type=PurchaseType.INVENTORY)
                for raw in items:
                    dp.add_line(DirectPurchaseLine.create(
                        str(raw["product_id"]), str(raw.get("description", "")),
                        str(raw["quantity"]),
                        Money(str(raw.get("unit_cost", "0")), currency_code)))
                dp.confirm()
                gr = self._build_receipt(dp, actor_user_id,
                                         uow.sequences.next_number("REC", _year()), uuid_qr)
                gr.complete()
                dp.mark_received()
            except (ProcurementDomainError, ValueError, KeyError) as exc:
                return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

            uow.direct_purchases.save(dp)
            uow.direct_purchases.set_operation_id(dp.id, operation_id)
            uow.receipts.save(gr)
            uow.direct_purchases.link_receipt(dp.id, gr.id)
            uow.qr_containers.mark_received(uuid_qr, receipt_id=gr.id,
                                            warehouse_id=warehouse_id)
            uow.audit.record(action=ProcurementEvents.DIRECT_PURCHASE_RECEIVED,
                             actor_user_id=actor_user_id, document_id=dp.id,
                             reason=f"Recepción QR {uuid_qr}", operation_id=operation_id,
                             branch_id=branch_id,
                             source_channel=SourceChannel.MOBILE_RECEIVING.value)

            self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_RECEIVED, document_id=dp.id,
                       operation_id=operation_id, actor_user_id=actor_user_id,
                       supplier_id=supplier_id, branch_id=branch_id,
                       warehouse_id=warehouse_id, goods_receipt_id=gr.id,
                       source_channel=SourceChannel.MOBILE_RECEIVING.value,
                       uuid_qr=uuid_qr,
                       inventory_lines=[{"product_id": ln.product_id,
                                         "quantity": str(ln.inventory_quantity()),
                                         "unit_cost": str(ln.unit_cost.amount)}
                                        for ln in dp.lines])
            if balance > 0:
                self._emit(uow, ProcurementEvents.PURCHASE_PAYABLE_CREATED, document_id=dp.id,
                           operation_id=operation_id, actor_user_id=actor_user_id,
                           supplier_id=supplier_id, amount=str(balance),
                           currency_code=currency_code, payment_condition="QR_BALANCE")
        return ProcurementResult.ok("Recepción QR registrada", entity_id=dp.id,
                                    operation_id=operation_id, status=dp.status.value,
                                    goods_receipt_id=gr.id, balance=str(balance))

    @staticmethod
    def _build_receipt(dp: DirectPurchase, actor_user_id: str, document_number,
                       uuid_qr: str) -> GoodsReceipt:
        gr = GoodsReceipt.create(document_number, dp.supplier_id, dp.branch_id,
                                 dp.warehouse_id, received_by_user_id=actor_user_id,
                                 direct_purchase_id=dp.id)
        for ln in dp.lines:
            qty = ln.inventory_quantity()
            gr.add_line(GoodsReceiptLine.create(ln.product_id, qty, qty, qty, lot=uuid_qr))
        return gr
