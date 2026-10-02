"""Adjudicación → órdenes de compra (Compras FASE 6).

Antes la adjudicación sólo escribía ``purchase_awards``/``purchase_award_lines`` y
ahí terminaba el flujo: no había forma de convertirla en órdenes, y aunque se
capturaran a mano, la primera orden marcaba la solicitud SOURCED y la segunda
(adjudicación dividida) era imposible.

Aquí: una orden por proveedor adjudicado, con el precio COTIZADO y la cantidad
ADJUDICADA, creada por el mismo `CreatePurchaseOrderUseCase` (mismas reglas del
maestro, mismo folio, misma cobertura de la solicitud). Idempotente por
(adjudicación, proveedor): reintentar completa sólo las que falten.
"""

from __future__ import annotations

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.exceptions import PurchasePermissionDeniedError
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)
from backend.shared.ids import new_uuid


class _GenerationAborted(Exception):
    """Revierte la transacción de «Generar órdenes» cuando un proveedor falla."""

    def __init__(self, supplier_id: str, result: ProcurementResult) -> None:
        super().__init__(result.message)
        self.supplier_id = supplier_id
        self.result = result


class GeneratePurchaseOrdersFromAwardUseCase:
    def __init__(self, create_order, authorization: PurchaseAuthorizationPolicy | None = None
                 ) -> None:
        self._create_order = create_order
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str, award_id: str,
                warehouse_id: str, payment_terms: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.ORDER_CREATE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        try:
            with ProcurementUnitOfWork(connection) as uow:
                award = uow.rfqs.get_award(award_id)
                if award is None:
                    return ProcurementResult.fail("Adjudicación inexistente", "NOT_FOUND",
                                                  operation_id=operation_id)
                rfq = uow.rfqs.get_rfq(award.rfq_id)
                requisition = (uow.requisitions.get(rfq.requisition_id)
                               if rfq is not None and rfq.requisition_id else None)
                if requisition is None:
                    return ProcurementResult.fail(
                        "La adjudicación no tiene una solicitud de origen",
                        "INVALID_REQUISITION", operation_id=operation_id)
                by_supplier: dict[str, list[dict]] = {}
                for award_line in award.lines:
                    found = uow.rfqs.get_quote_line(award_line.quote_line_id)
                    if found is None:
                        return ProcurementResult.fail(
                            "Una línea adjudicada ya no existe en la cotización", "NOT_FOUND",
                            operation_id=operation_id)
                    _supplier, quote_line = found
                    by_supplier.setdefault(award_line.supplier_id, []).append({
                        "product_id": quote_line.product_id,
                        "quantity": str(award_line.awarded_quantity),
                        "unit_price": str(quote_line.unit_price.amount),
                        "purchase_nature": quote_line.purchase_nature.value,
                    })
                orders = []
                # Todas en la MISMA transacción: si la de un proveedor falla, se
                # revierten las demás (antes quedaban creadas a medias).
                for supplier_id in sorted(by_supplier):
                    result = self._create_order.create_in(
                        uow, actor_user_id=actor_user_id, operation_id=new_uuid(),
                        supplier_id=supplier_id, branch_id=requisition.branch_id,
                        warehouse_id=warehouse_id, lines=by_supplier[supplier_id],
                        requisition_id=requisition.id, rfq_id=rfq.id, award_id=award_id,
                        payment_terms=payment_terms)
                    if not result.success:
                        raise _GenerationAborted(supplier_id, result)
                    orders.append({"supplier_id": supplier_id, "entity_id": result.entity_id,
                                   "document_number": result.data.get("document_number", ""),
                                   "already_registered": bool(
                                       result.data.get("already_registered"))})
        except _GenerationAborted as aborted:
            return ProcurementResult.fail(
                "No se generó ninguna orden: " + aborted.result.message,
                aborted.result.error_code or "VALIDATION", operation_id=operation_id,
                orders=[], failures=[{"supplier_id": aborted.supplier_id,
                                      "message": aborted.result.message,
                                      "error_code": aborted.result.error_code}])
        created = [o for o in orders if not o["already_registered"]]
        message = ("Las órdenes de esta adjudicación ya estaban generadas" if not created
                   else f"{len(created)} orden(es) generada(s)")
        return ProcurementResult.ok(message, entity_id=award_id, operation_id=operation_id,
                                    orders=orders, failures=[])
