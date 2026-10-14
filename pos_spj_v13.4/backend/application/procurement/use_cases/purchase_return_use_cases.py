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
from decimal import Decimal

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


def _return_basis(uow, gr) -> dict[str, dict]:
    """Por línea recibida: producto, cantidad todavía retornable (aceptado menos
    devoluciones no canceladas), factor a unidad de inventario y costo/IVA por
    unidad de la recepción (auditoría Compras C13)."""
    from backend.application.procurement.product_master_rules import inventory_unit_cost

    returned: dict[str, Decimal] = {}
    for other in uow.returns.list_by_goods_receipt(gr.id):
        if other.status.value == "CANCELLED":
            continue
        for ln in other.lines:
            if ln.goods_receipt_line_id:
                returned[ln.goods_receipt_line_id] = (
                    returned.get(ln.goods_receipt_line_id, Decimal("0")) + ln.quantity)
    basis: dict[str, dict] = {}
    if gr.purchase_order_id:
        po = uow.orders.get(gr.purchase_order_id)
        by_id = {ln.id: ln for ln in po.lines} if po else {}
        by_product = {ln.product_id: ln for ln in po.lines} if po else {}
        for ln in gr.lines:
            src = by_id.get(ln.purchase_order_line_id or "") or by_product.get(ln.product_id)
            factor = (src.conversion_factor if src else None) or Decimal("1")
            billable = src.billable_quantity() if src else Decimal("0")
            net = ((src.unit_price.amount - src.discount / billable) if src and billable > 0
                   else (src.unit_price.amount if src else Decimal("0")))
            basis[ln.id] = {
                "product_id": ln.product_id,
                "available": ln.accepted_quantity - returned.get(ln.id, Decimal("0")),
                "factor": Decimal(str(factor)),
                "unit_cost": inventory_unit_cost(net, factor),
                "tax_per_unit": (src.tax / billable if src and billable > 0 else Decimal("0")),
                "currency": po.currency_code if po else "MXN",
            }
    elif gr.direct_purchase_id:
        dp = uow.direct_purchases.get(gr.direct_purchase_id)
        by_id = {ln.id: ln for ln in dp.lines} if dp else {}
        by_product = {ln.product_id: ln for ln in dp.lines} if dp else {}
        for ln in gr.lines:
            src = by_id.get(ln.direct_purchase_line_id or "") or by_product.get(ln.product_id)
            inventory = src.inventory_quantity() if src else Decimal("0")
            basis[ln.id] = {
                "product_id": ln.product_id,
                "available": ln.accepted_quantity - returned.get(ln.id, Decimal("0")),
                "factor": Decimal("1"),   # la recepción directa ya está en inventario
                "unit_cost": src.inventory_unit_cost() if src else Decimal("0"),
                "tax_per_unit": (src.tax.amount / inventory if src and inventory > 0
                                 else Decimal("0")),
                "currency": dp.currency_code if dp else "MXN",
            }
    return basis


def _applied_invoice_ids(uow, gr) -> list[str]:
    rows = uow.invoices.invoiced_quantities(purchase_order_id=gr.purchase_order_id,
                                            direct_purchase_id=gr.direct_purchase_id) \
        if (gr.purchase_order_id or gr.direct_purchase_id) else []
    seen: list[str] = []
    for row in rows:
        if row["status"] in ("MATCHED", "APPROVED", "POSTED") and row["invoice_id"] not in seen:
            seen.append(row["invoice_id"])
    return seen


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
            self._auth.require_branch(actor_user_id, branch_id)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            existing = uow.returns.get_by_operation(operation_id)
            if existing is not None:
                return ProcurementResult.ok("Devolución ya registrada", entity_id=existing.id,
                                            operation_id=operation_id,
                                            status=existing.status.value)
            # Auditoría C13: una devolución sale de una recepción concreta, del
            # mismo proveedor, almacén y producto, y no excede lo que aún se
            # puede devolver de cada línea recibida.
            gr = uow.receipts.get(goods_receipt_id) if goods_receipt_id else None
            if gr is None or gr.status != "COMPLETED":
                return ProcurementResult.fail(
                    "La devolución debe referir una recepción completada", "VALIDATION",
                    operation_id=operation_id)
            if gr.supplier_id != supplier_id:
                return ProcurementResult.fail(
                    "La recepción es de otro proveedor", "SUPPLIER_MISMATCH",
                    operation_id=operation_id)
            if gr.branch_id != branch_id or gr.warehouse_id != warehouse_id:
                return ProcurementResult.fail(
                    "La devolución sale del almacén y la sucursal de la recepción",
                    "VALIDATION", operation_id=operation_id)
            purchase_order_id = gr.purchase_order_id
            basis = _return_basis(uow, gr)
            by_product = {}
            for gr_line in gr.lines:
                by_product.setdefault(gr_line.product_id, []).append(gr_line.id)
            requested: dict[str, Decimal] = {}
            try:
                pr = PurchaseReturn.create(
                    uow.sequences.next_number("DEV", _year()), supplier_id, branch_id,
                    warehouse_id, PurchaseReturnReason(reason),
                    created_by_user_id=actor_user_id, goods_receipt_id=goods_receipt_id,
                    purchase_order_id=purchase_order_id)
                for raw in lines:
                    line_id = raw.get("goods_receipt_line_id")
                    if not line_id:
                        candidates = by_product.get(raw["product_id"], [])
                        if len(candidates) != 1:
                            return ProcurementResult.fail(
                                "Indique la línea recibida que se devuelve", "VALIDATION",
                                operation_id=operation_id)
                        line_id = candidates[0]
                    source = basis.get(line_id)
                    if source is None:
                        return ProcurementResult.fail(
                            "La línea devuelta no pertenece a la recepción", "VALIDATION",
                            operation_id=operation_id)
                    if source["product_id"] != raw["product_id"]:
                        return ProcurementResult.fail(
                            "El producto devuelto no es el de la línea recibida",
                            "PRODUCT_MISMATCH", operation_id=operation_id)
                    quantity = Decimal(str(raw["quantity"]))
                    requested[line_id] = requested.get(line_id, Decimal("0")) + quantity
                    if requested[line_id] > source["available"]:
                        return ProcurementResult.fail(
                            f"Se devuelve más de lo recibido disponible ({source['available']})",
                            "OVER_RETURN", operation_id=operation_id)
                    cost = Money(str(raw["unit_cost"]) if raw.get("unit_cost") is not None
                                 else source["unit_cost"] * source["factor"],
                                 source["currency"])
                    pr.add_line(PurchaseReturnLine.create(
                        raw["product_id"], str(quantity), unit_cost=cost,
                        lot=raw.get("lot"), goods_receipt_line_id=line_id,
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
            # Inventory's SupplierReturnHandler (event_handlers/inventory/
            # supplier_return_handler.py) already consumes PURCHASE_RETURN_CREATED
            # and posts a SUPPLIER_RETURN outbound movement — it just isn't
            # live-wired to the bus yet (deliberately gated behind the INV-27
            # cutover, same as GoodsReceiptReversedHandler). The payload below is
            # shaped to match what it expects (resolve_ingress + per-line
            # product_id/quantity/unit_cost/lot_id) so it's correct once that
            # cutover flips the subscription on.
            _emit(uow, ProcurementEvents.PURCHASE_RETURN_CREATED, document_id=pr.id,
                  operation_id=operation_id, actor_user_id=actor_user_id, branch_id=branch_id,
                  supplier_id=supplier_id, document_number=pr.document_number,
                  goods_receipt_id=goods_receipt_id, purchase_order_id=purchase_order_id,
                  warehouse_id=warehouse_id,
                  lines=[{"product_id": ln.product_id, "quantity": str(ln.quantity),
                          "unit_cost": ln.unit_cost.to_string() if ln.unit_cost else None,
                          "lot_id": ln.lot} for ln in pr.lines])
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
            gr = uow.receipts.get(pr.goods_receipt_id) if pr.goods_receipt_id else None
            if gr is None:
                return ProcurementResult.fail(
                    "La devolución no refiere una recepción", "VALIDATION",
                    operation_id=operation_id)
            # Otra devolución pudo confirmarse desde el borrador: se revalida
            # contra lo confirmado por las DEMÁS (esta cuenta como borrador).
            basis = _return_basis(uow, gr)
            mine: dict[str, Decimal] = {}
            for ln in pr.lines:
                mine[ln.goods_receipt_line_id] = mine.get(ln.goods_receipt_line_id,
                                                          Decimal("0")) + ln.quantity
            for line_id, quantity in mine.items():
                source = basis.get(line_id)
                if source is None or source["available"] + quantity < quantity:
                    return ProcurementResult.fail(
                        "Lo devuelto ya no está disponible en la recepción", "OVER_RETURN",
                        operation_id=operation_id)
            try:
                pr.confirm()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            currency = next(iter(basis.values()))["currency"] if basis else "MXN"
            value = Decimal("0")
            tax = Decimal("0")
            stock_lines = []
            for ln in pr.lines:
                source = basis[ln.goods_receipt_line_id]
                inventory_quantity = ln.quantity * source["factor"]
                unit_cost = (ln.unit_cost.amount / source["factor"] if ln.unit_cost
                             else source["unit_cost"])
                value += inventory_quantity * unit_cost
                tax += ln.quantity * source["tax_per_unit"]
                stock_lines.append({"product_id": ln.product_id,
                                    "quantity": str(inventory_quantity),
                                    "unit_cost": str(unit_cost), "lot_code": ln.lot,
                                    "from_location_id": pr.branch_id})
            uow.returns.save(pr)
            uow.audit.record(action=ProcurementEvents.PURCHASE_RETURN_CONFIRMED,
                             actor_user_id=actor_user_id, document_id=pr.id,
                             operation_id=operation_id, branch_id=pr.branch_id)
            # C12: AQUÍ sale la mercancía (no en el borrador). Inventario
            # registra la salida; Finanzas aplica la nota de crédito.
            _emit(uow, ProcurementEvents.PURCHASE_RETURN_CONFIRMED, document_id=pr.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  branch_id=pr.branch_id, supplier_id=pr.supplier_id,
                  warehouse_id=pr.warehouse_id, return_id=pr.id,
                  goods_receipt_id=pr.goods_receipt_id,
                  document_number=pr.document_number, currency_code=currency,
                  return_value=str(value.quantize(Decimal("0.01"))),
                  return_tax=str(tax.quantize(Decimal("0.01"))),
                  invoice_ids=_applied_invoice_ids(uow, gr), lines=stock_lines)
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
