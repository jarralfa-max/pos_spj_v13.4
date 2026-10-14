"""Resolución explícita de faltantes y facturas erróneas (auditoría Compras d9f2bca).

- C09/C10: un rechazo ya no cierra la orden ni la compra directa: lo que falta
  queda pendiente de reposición. Cuando el proveedor NO repondrá, alguien con
  permiso cierra el faltante con motivo; queda en auditoría y en el evento.
- C22: una factura capturada por error (aún no conciliada ni aprobada) se
  cancela con motivo y deja de reservar cantidad facturable.
"""

from __future__ import annotations

import json

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.events import ProcurementEvents, build_event_payload
from backend.domain.procurement.exceptions import (
    ProcurementDomainError,
    PurchasePermissionDeniedError,
)
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


def _emit(uow, event_name, *, document_id, operation_id, actor_user_id=None, **extra):
    payload = build_event_payload(event_name, operation_id=operation_id,
                                  document_id=document_id, user_id=actor_user_id, **extra)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


def _require(auth, actor_user_id, code, operation_id, reason):
    try:
        auth.require(actor_user_id, code)
    except PurchasePermissionDeniedError as exc:
        return ProcurementResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
    if not reason or not reason.strip():
        return ProcurementResult.fail("Se requiere el motivo", "VALIDATION",
                                      operation_id=operation_id)
    return None


class ClosePurchaseOrderRemainderUseCase:
    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, purchase_order_id: str,
                operation_id: str, reason: str) -> ProcurementResult:
        denied = _require(self._auth, actor_user_id, PurchasePermissions.ORDER_CLOSE,
                          operation_id, reason)
        if denied is not None:
            return denied
        with ProcurementUnitOfWork(connection) as uow:
            po = uow.orders.get(purchase_order_id)
            if po is None:
                return ProcurementResult.fail("Orden inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            pending = {ln.id: str(ln.ordered_quantity - ln.accepted_quantity)
                       for ln in po.lines if ln.ordered_quantity > ln.accepted_quantity}
            try:
                po.close_remainder()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            uow.orders.save(po)
            uow.audit.record(action=ProcurementEvents.PURCHASE_ORDER_REMAINDER_CLOSED,
                             actor_user_id=actor_user_id, document_id=po.id,
                             reason=reason.strip(), operation_id=operation_id,
                             branch_id=po.branch_id, after_json=json.dumps(pending))
            _emit(uow, ProcurementEvents.PURCHASE_ORDER_REMAINDER_CLOSED, document_id=po.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  branch_id=po.branch_id, supplier_id=po.supplier_id,
                  reason=reason.strip(), closed_quantities=pending)
        return ProcurementResult.ok("Faltante cerrado", entity_id=po.id,
                                    operation_id=operation_id, status=po.status.value)


class CloseDirectPurchaseRemainderUseCase:
    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, direct_purchase_id: str,
                operation_id: str, reason: str) -> ProcurementResult:
        denied = _require(self._auth, actor_user_id, PurchasePermissions.RECEIPT_REJECT,
                          operation_id, reason)
        if denied is not None:
            return denied
        with ProcurementUnitOfWork(connection) as uow:
            dp = uow.direct_purchases.get(direct_purchase_id)
            if dp is None:
                return ProcurementResult.fail("Compra directa inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            try:
                dp.close_remainder()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            uow.direct_purchases.save(dp)
            uow.audit.record(action=ProcurementEvents.DIRECT_PURCHASE_REMAINDER_CLOSED,
                             actor_user_id=actor_user_id, document_id=dp.id,
                             reason=reason.strip(), operation_id=operation_id,
                             branch_id=dp.branch_id)
            _emit(uow, ProcurementEvents.DIRECT_PURCHASE_REMAINDER_CLOSED, document_id=dp.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  branch_id=dp.branch_id, supplier_id=dp.supplier_id, reason=reason.strip())
        return ProcurementResult.ok("Faltante cerrado", entity_id=dp.id,
                                    operation_id=operation_id, status=dp.status.value)


class CancelSupplierInvoiceUseCase:
    """Sólo antes de generar deuda: CAPTURED, WITH_DIFFERENCES o BLOCKED."""

    _CANCELLABLE = frozenset({"CAPTURED", "PENDING_MATCH", "WITH_DIFFERENCES", "BLOCKED"})

    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, invoice_id: str,
                operation_id: str, reason: str) -> ProcurementResult:
        denied = _require(self._auth, actor_user_id, PurchasePermissions.INVOICE_CANCEL,
                          operation_id, reason)
        if denied is not None:
            return denied
        with ProcurementUnitOfWork(connection) as uow:
            inv = uow.invoices.get(invoice_id)
            if inv is None:
                return ProcurementResult.fail("Factura inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            if inv.status == "CANCELLED":
                return ProcurementResult.ok("Factura ya cancelada", entity_id=inv.id,
                                            operation_id=operation_id, status=inv.status)
            if inv.status not in self._CANCELLABLE:
                return ProcurementResult.fail(
                    "La factura ya generó deuda; su corrección es una nota de crédito",
                    "INVALID_STATE", operation_id=operation_id)
            uow.invoices.cancel(inv.id)
            uow.audit.record(action=ProcurementEvents.SUPPLIER_INVOICE_CANCELLED,
                             actor_user_id=actor_user_id, document_id=inv.id,
                             reason=reason.strip(), operation_id=operation_id)
            _emit(uow, ProcurementEvents.SUPPLIER_INVOICE_CANCELLED, document_id=inv.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  supplier_id=inv.supplier_id, reason=reason.strip())
        return ProcurementResult.ok("Factura cancelada", entity_id=invoice_id,
                                    operation_id=operation_id, status="CANCELLED")
