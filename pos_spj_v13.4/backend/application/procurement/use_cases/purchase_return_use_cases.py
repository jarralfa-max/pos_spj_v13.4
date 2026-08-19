"""Purchase-return (devolución a proveedor) use cases.

A confirmed goods receipt occasionally needs to send stock back to the
supplier — quality failure, damage, wrong product, excess, expired goods,
sanitary failure, or a commercial agreement. The original receipt is never
deleted (it stays as history); the return is its own document that may
reference it (``goods_receipt_id``) and/or the source order
(``purchase_order_id``). Kept intentionally simple — DRAFT → CONFIRMED, or
DRAFT → CANCELLED — unlike the multi-stage requisition/approval workflow.

Every transition re-validates ``COMPRAS.recepcion.devolucion``, is atomic via
``ProcurementUnitOfWork``, is audited, and publishes its canonical event
post-commit through the outbox — same pattern as every other procurement use
case (see ``requisition_use_cases.py``).
"""

from __future__ import annotations

import json

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.entities import PurchaseReturn, PurchaseReturnLine
from backend.domain.procurement.enums import PurchaseReturnReason
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


def _emit(uow, event_name, *, document_id, operation_id, actor_user_id=None, **extra):
    payload = build_event_payload(event_name, operation_id=operation_id,
                                  document_id=document_id, user_id=actor_user_id, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


class CreatePurchaseReturnUseCase:
    """Drafts a purchase return, optionally against a prior goods receipt/order."""

    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str, supplier_id: str,
                branch_id: str, warehouse_id: str, reason: str, lines: list[dict],
                goods_receipt_id: str | None = None,
                purchase_order_id: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RETURN)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            existing = uow.returns.get_by_operation(operation_id)
            if existing is not None:
                return ProcurementResult.ok("Devolución ya registrada", entity_id=existing.id,
                                            operation_id=operation_id,
                                            status=existing.status.value)
            try:
                pr = PurchaseReturn.create(
                    uow.sequences.next_number("DEV", _year()), supplier_id, branch_id,
                    warehouse_id, PurchaseReturnReason(reason),
                    created_by_user_id=actor_user_id, goods_receipt_id=goods_receipt_id,
                    purchase_order_id=purchase_order_id)
                for raw in lines:
                    cost = (Money(str(raw["unit_cost"]))
                            if raw.get("unit_cost") is not None else None)
                    pr.add_line(PurchaseReturnLine.create(
                        raw["product_id"], str(raw["quantity"]), unit_cost=cost,
                        lot=raw.get("lot"),
                        goods_receipt_line_id=raw.get("goods_receipt_line_id"),
                        notes=raw.get("notes", "")))
                if not pr.lines:
                    return ProcurementResult.fail("La devolución requiere al menos una línea",
                                                  "EMPTY", operation_id=operation_id)
            except (ProcurementDomainError, ValueError) as exc:
                return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.returns.save(pr)
            uow.returns.set_operation_id(pr.id, operation_id)
            uow.audit.record(action=ProcurementEvents.PURCHASE_RETURN_CREATED,
                             actor_user_id=actor_user_id, document_id=pr.id,
                             reason="alta devolución a proveedor", operation_id=operation_id,
                             branch_id=branch_id)
            # FOLLOW-UP: a purchase return should also emit an inventory outbound
            # movement (stock leaves because it's being returned to the supplier).
            # Not wired here — the Inventory bounded context does not yet expose a
            # write port/translator target for outbound procurement-return
            # movements (mirrors GOODS_RECEIPT_COMPLETED -> on_receipt_completed in
            # integrations/downstream_translators.py + wiring.py); a separate task
            # is formalizing missing ports and will add that translation.
            _emit(uow, ProcurementEvents.PURCHASE_RETURN_CREATED, document_id=pr.id,
                  operation_id=operation_id, actor_user_id=actor_user_id, branch_id=branch_id,
                  supplier_id=supplier_id, document_number=pr.document_number,
                  goods_receipt_id=goods_receipt_id, purchase_order_id=purchase_order_id,
                  warehouse_id=warehouse_id,
                  lines=[{"product_id": ln.product_id, "quantity": str(ln.quantity),
                          "unit_cost": ln.unit_cost.to_string() if ln.unit_cost else None,
                          "lot": ln.lot} for ln in pr.lines])
        return ProcurementResult.ok("Devolución creada", entity_id=pr.id,
                                    operation_id=operation_id, status=pr.status.value,
                                    document_number=pr.document_number)


class ConfirmPurchaseReturnUseCase:
    """Confirms a draft return. This is the point at which stock actually leaves
    for the supplier — the inventory downstream translation (follow-up, see
    ``CreatePurchaseReturnUseCase``) should hook onto ``PURCHASE_RETURN_CONFIRMED``."""

    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, purchase_return_id: str,
                operation_id: str) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RETURN)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            pr = uow.returns.get(purchase_return_id)
            if pr is None:
                return ProcurementResult.fail("Devolución inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            try:
                pr.confirm()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            uow.returns.save(pr)
            uow.audit.record(action=ProcurementEvents.PURCHASE_RETURN_CONFIRMED,
                             actor_user_id=actor_user_id, document_id=pr.id,
                             operation_id=operation_id, branch_id=pr.branch_id)
            _emit(uow, ProcurementEvents.PURCHASE_RETURN_CONFIRMED, document_id=pr.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  branch_id=pr.branch_id, supplier_id=pr.supplier_id,
                  document_number=pr.document_number,
                  lines=[{"product_id": ln.product_id, "quantity": str(ln.quantity)}
                         for ln in pr.lines])
        return ProcurementResult.ok("Devolución confirmada", entity_id=pr.id,
                                    operation_id=operation_id, status=pr.status.value)


class CancelPurchaseReturnUseCase:
    """Cancels a draft return (a confirmed return cannot be cancelled — the stock
    movement already happened; a compensating document would be a new return)."""

    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, purchase_return_id: str,
                operation_id: str, reason: str = "") -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RETURN)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            pr = uow.returns.get(purchase_return_id)
            if pr is None:
                return ProcurementResult.fail("Devolución inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            try:
                pr.cancel()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            uow.returns.save(pr)
            uow.audit.record(action=ProcurementEvents.PURCHASE_RETURN_CANCELLED,
                             actor_user_id=actor_user_id, document_id=pr.id, reason=reason,
                             operation_id=operation_id, branch_id=pr.branch_id)
            _emit(uow, ProcurementEvents.PURCHASE_RETURN_CANCELLED, document_id=pr.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  branch_id=pr.branch_id)
        return ProcurementResult.ok("Devolución cancelada", entity_id=pr.id,
                                    operation_id=operation_id, status=pr.status.value)
