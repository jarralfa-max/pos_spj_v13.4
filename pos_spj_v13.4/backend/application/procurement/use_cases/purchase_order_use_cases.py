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
from backend.application.procurement.product_master_rules import (
    fraction_problem,
    inventory_unit_cost,
    product_problem,
    units_from_product_master,
    warehouse_problem,
)
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
    PurchaseNature,
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
    """Alta de orden de compra. Aplica las MISMAS reglas del maestro que la compra
    rápida (`product_master_rules`): almacén de la sucursal, producto activo y
    comprable, unidad de compra configurada en Productos (el factor lo deriva el
    maestro, nunca la pantalla). Todo se valida ANTES de reservar el folio: antes
    una línea inválida consumía un número OC y dejaba un hueco en la secuencia."""

    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None,
                 supplier_directory=None, *, product_catalog=None,
                 warehouse_directory=None, supplier_origins=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._supplier_directory = supplier_directory
        self._product_catalog = product_catalog
        self._warehouse_directory = warehouse_directory
        # Bodegas/puntos de recolección del proveedor (Supplier Master, §13).
        self._supplier_origins = supplier_origins

    def execute(self, connection, *, actor_user_id: str, operation_id: str, supplier_id: str,
                branch_id: str, warehouse_id: str, lines: list[dict],
                purchase_type: str = PurchaseType.INVENTORY.value, currency_code: str = "MXN",
                requisition_id: str | None = None, rfq_id: str | None = None,
                award_id: str | None = None,
                payment_terms: str | None = None, **header) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.ORDER_CREATE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            return self.create_in(
                uow, actor_user_id=actor_user_id, operation_id=operation_id,
                supplier_id=supplier_id, branch_id=branch_id, warehouse_id=warehouse_id,
                lines=lines, purchase_type=purchase_type, currency_code=currency_code,
                requisition_id=requisition_id, rfq_id=rfq_id, award_id=award_id,
                payment_terms=payment_terms, **header)

    def _pickup_origin(self, header: dict, supplier_id: str) -> tuple[dict, str | None]:
        """Recolección en proveedor: la bodega/punto de recolección es obligatoria,
        debe ser DEL proveedor, y se guarda con una foto del domicilio (§13)."""
        address_id = header.get("origin_supplier_address_id")
        pickup = header.get("delivery_method") == "SUPPLIER_PICKUP"
        if not address_id:
            if pickup:
                return header, ("Para recolección en proveedor elige la bodega o punto de "
                                "recolección")
            return header, None
        if self._supplier_origins is None:
            return header, None
        origin = self._supplier_origins.origin_location(supplier_id, address_id)
        if origin is None:
            return header, ("La bodega o punto de recolección no pertenece al proveedor "
                            "elegido")
        return dict(header, origin_address_snapshot=json.dumps(origin["snapshot"],
                                                               ensure_ascii=False)), None

    def create_in(self, uow, *, actor_user_id: str, operation_id: str, supplier_id: str,
                  branch_id: str, warehouse_id: str, lines: list[dict],
                  purchase_type: str = PurchaseType.INVENTORY.value,
                  currency_code: str = "MXN", requisition_id: str | None = None,
                  rfq_id: str | None = None, award_id: str | None = None,
                  payment_terms: str | None = None, **header) -> ProcurementResult:
        """Crea la orden DENTRO de la transacción ``uow`` (sin autorizar: quien
        llama ya lo hizo). Así «Generar órdenes» crea las de todos los
        proveedores en UNA transacción: o se generan todas o ninguna."""
        existing = uow.orders.get_by_operation(operation_id)
        if existing is None and award_id:
            # Una orden por (adjudicación, proveedor): reintentar "Generar
            # órdenes" devuelve la que ya existe (índice único, migración 278).
            existing = uow.orders.get_by_award_supplier(award_id, supplier_id)
        if existing is not None:
            return ProcurementResult.ok("Orden ya registrada", entity_id=existing.id,
                                        operation_id=operation_id,
                                        status=existing.status.value,
                                        document_number=existing.document_number,
                                        already_registered=True)
        try:
            header, problema = _order_header(header, currency_code)
            if problema is None:
                header, problema = self._pickup_origin(header, supplier_id)
            if problema is not None:
                return ProcurementResult.fail(problema, "VALIDATION", operation_id=operation_id)
            source_requisition = None
            if requisition_id:
                source_requisition = uow.requisitions.get(requisition_id)
                # Aprobada o surtida en parte: una solicitud puede cubrirse
                # con varias órdenes (adjudicación dividida, abasto parcial).
                if source_requisition is None or not source_requisition.can_be_sourced():
                    return ProcurementResult.fail(
                        "La orden requiere una solicitud aprobada",
                        "INVALID_REQUISITION", operation_id=operation_id)
            if self._supplier_directory is not None:
                self._supplier_directory.require_eligible(supplier_id)
            problema = warehouse_problem(self._warehouse_directory, branch_id, warehouse_id)
            if problema is not None:
                return ProcurementResult.fail(problema[1], problema[0],
                                              operation_id=operation_id)
            order_lines = []
            for raw in lines:
                label = raw.get("description") or raw.get("product_id", "")
                problema = product_problem(self._product_catalog, raw.get("product_id"),
                                           label)
                if problema is None:
                    raw, problema = units_from_product_master(raw, self._product_catalog,
                                                              weight_known=False)
                if problema is not None:
                    return ProcurementResult.fail(problema[1], problema[0],
                                                  operation_id=operation_id)
                if raw.get("unit_price") in (None, ""):
                    return ProcurementResult.fail(
                        f"Captura el precio de {label}", "VALIDATION",
                        operation_id=operation_id)
                order_lines.append(PurchaseOrderLine.create(
                    raw["product_id"], raw.get("description", ""), str(raw["quantity"]),
                    Money(str(raw["unit_price"]), currency_code),
                    purchase_nature=PurchaseNature(
                        raw.get("purchase_nature", PurchaseNature.INVENTORY.value)),
                    conversion_factor=Decimal(str(raw.get("conversion_factor") or "1")),
                    purchase_unit=raw.get("purchase_unit") or "",
                    inventory_unit=raw.get("inventory_unit") or "",
                    discount=raw.get("discount") or "0", tax=raw.get("tax") or "0",
                    destination_warehouse_id=raw.get("destination_warehouse_id"),
                    pricing_basis=raw.get("pricing_basis") or "",
                    inventory_by_weight=bool(raw.get("inventory_by_weight"))))
            if not order_lines:
                return ProcurementResult.fail("La orden requiere al menos una línea",
                                              "EMPTY", operation_id=operation_id)
            po = PurchaseOrder.create(
                uow.sequences.next_number("OC", _year()), supplier_id, branch_id,
                warehouse_id, created_by_user_id=actor_user_id,
                purchase_type=PurchaseType(purchase_type), currency_code=currency_code,
                payment_terms=payment_terms, **header)
            po.source_requisition_id = requisition_id
            po.source_rfq_id = rfq_id
            po.source_award_id = award_id
            po.lines.extend(order_lines)
        except (ProcurementDomainError, ValueError) as exc:
            return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
        uow.orders.save(po)
        uow.orders.set_operation_id(po.id, operation_id)
        uow.orders.record_version(po, before=None, reason="alta", changed_by_user_id=actor_user_id)
        if source_requisition is not None:
            covered = _requisition_fully_covered(
                source_requisition, uow.orders.list_by_requisition(requisition_id), po)
            source_requisition.mark_sourced(partial=not covered)
            uow.requisitions.save(source_requisition)
        uow.audit.record(action=ProcurementEvents.PURCHASE_ORDER_CREATED,
                         actor_user_id=actor_user_id, document_id=po.id,
                         reason="alta orden", operation_id=operation_id, branch_id=branch_id)
        _emit(uow, ProcurementEvents.PURCHASE_ORDER_CREATED, document_id=po.id,
              operation_id=operation_id, actor_user_id=actor_user_id, supplier_id=supplier_id,
              branch_id=branch_id, document_number=po.document_number,
              total=str(po.total().amount), requisition_id=requisition_id,
              rfq_id=rfq_id, award_id=award_id)
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
                operation_id: str) -> ProcurementResult:
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
                # Enviar NO es aceptar (§24): la confirmación del proveedor se
                # registra aparte, con sus datos (AcknowledgePurchaseOrderUseCase).
                po.send()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            uow.orders.save(po)
            event = ProcurementEvents.PURCHASE_ORDER_SENT
            uow.audit.record(action=event, actor_user_id=actor_user_id, document_id=po.id,
                             operation_id=operation_id)
            _emit(uow, event, document_id=po.id, operation_id=operation_id,
                  actor_user_id=actor_user_id, supplier_id=po.supplier_id)
        return ProcurementResult.ok("Orden enviada", entity_id=po.id,
                                    operation_id=operation_id, status=po.status.value)


class AcknowledgePurchaseOrderUseCase:
    """El proveedor confirma una orden ENVIADA (§24): su referencia, la fecha de
    entrega que promete, las cantidades que confirma por línea y comentarios. Las
    diferencias contra lo pedido quedan como EXCEPCIONES en la orden y en el
    evento, para que Compras las vea antes de recibir."""

    def __init__(self, authorization=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, purchase_order_id: str,
                operation_id: str, supplier_reference: str = "",
                confirmed_delivery_date: str | None = None,
                confirmed_quantities: dict | None = None,
                comments: str = "", line_labels: dict | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.ORDER_ACKNOWLEDGE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            po = uow.orders.get(purchase_order_id)
            if po is None:
                return ProcurementResult.fail("Orden inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            if po.status is PurchaseOrderStatus.ACKNOWLEDGED:
                return ProcurementResult.ok("La orden ya estaba confirmada", entity_id=po.id,
                                            operation_id=operation_id,
                                            status=po.status.value, already_registered=True)
            try:
                exceptions = po.acknowledge(
                    supplier_reference=supplier_reference,
                    confirmed_delivery_date=confirmed_delivery_date,
                    confirmed_quantities={k: Decimal(str(v)) for k, v in
                                          (confirmed_quantities or {}).items()},
                    comments=comments, confirmed_by_user_id=actor_user_id,
                    line_labels=line_labels)
            except (ProcurementDomainError, ValueError, ArithmeticError) as exc:
                return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.orders.save(po)
            uow.audit.record(action=ProcurementEvents.PURCHASE_ORDER_ACKNOWLEDGED,
                             actor_user_id=actor_user_id, document_id=po.id,
                             reason=po.supplier_reference or "confirmación del proveedor",
                             operation_id=operation_id)
            _emit(uow, ProcurementEvents.PURCHASE_ORDER_ACKNOWLEDGED, document_id=po.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  supplier_id=po.supplier_id, supplier_reference=po.supplier_reference,
                  confirmed_delivery_date=po.confirmed_delivery_date,
                  exceptions=exceptions)
        message = ("Confirmación registrada con excepciones" if exceptions
                   else "Confirmación registrada")
        return ProcurementResult.ok(message, entity_id=po.id, operation_id=operation_id,
                                    status=po.status.value, exceptions=exceptions)


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
    cannot also be the price changer (segregation).

    FASE 10-11 (2026-09-29): el MISMO perfil de Productos que guió la compra guía
    la recepción (§25) — lote, caducidad, peso real y temperatura se exigen cuando
    el producto lo indica, sin reglas por categoría —; una línea recibida puede
    apuntar a su línea de OC (varias recepciones del mismo producto con lotes
    distintos); lo rechazado queda como diferencia; es idempotente por operación y
    puede venir de un embarque de Logística (``shipment_id``)."""

    def __init__(self, authorization=None, *, tolerance: Tolerance | None = None,
                 product_catalog=None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()
        self._tolerance = tolerance or Tolerance(Decimal("0"))
        self._tol_policy = ReceiptTolerancePolicy()
        self._sod = SegregationOfDutiesPolicy()
        self._catalog = product_catalog

    def execute(self, connection, *, actor_user_id: str, purchase_order_id: str,
                operation_id: str, receipt_lines: list[dict],
                price_changer_id: str | None = None,
                has_over_receive_permission: bool = False,
                shipment_id: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RECEIPT_COMPLETE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            existing = uow.receipts.get_by_operation(operation_id)
            if existing is not None:
                return ProcurementResult.ok("Recepción ya registrada", entity_id=existing.id,
                                            operation_id=operation_id,
                                            already_registered=True)
            po = uow.orders.get(purchase_order_id)
            if po is None:
                return ProcurementResult.fail("Orden inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            lines_by_id = {ln.id: ln for ln in po.lines}
            lines_by_product = {ln.product_id: ln for ln in po.lines}
            try:
                if price_changer_id:
                    self._sod.enforce_receiver_not_price_changer(actor_user_id, price_changer_id)
                gr = GoodsReceipt.create(
                    uow.sequences.next_number("REC", _year()), po.supplier_id, po.branch_id,
                    po.warehouse_id, received_by_user_id=actor_user_id,
                    purchase_order_id=po.id, shipment_id=shipment_id)
                received_by_line: dict[str, Decimal] = {}
                for raw in receipt_lines:
                    product_id = raw["product_id"]
                    po_line = (lines_by_id.get(raw.get("purchase_order_line_id"))
                               or lines_by_product.get(product_id))
                    ordered = po_line.ordered_quantity if po_line else Decimal("0")
                    received = Decimal(str(raw["received_quantity"]))
                    accepted = Decimal(str(raw.get("accepted_quantity", raw["received_quantity"])))
                    extra = _receipt_capture(raw)
                    problem = self._profile_problem(product_id, accepted, extra,
                                                    label=po_line.description if po_line else "")
                    if problem is None and po_line is not None:
                        problem = fraction_problem(
                            self._catalog, product_id, po_line.purchase_unit,
                            (received, accepted), po_line.description)
                    if problem is not None:
                        return ProcurementResult.fail(problem, "VALIDATION",
                                                      operation_id=operation_id)
                    already = received_by_line.get(po_line.id, Decimal("0")) if po_line else \
                        Decimal("0")
                    has_override = False
                    total_received = already + received
                    if total_received > ordered and not self._tolerance.within(ordered, total_received):
                        try:
                            self._auth.require(
                                actor_user_id, PurchasePermissions.RECEIPT_OVER_TOLERANCE)
                            has_override = True
                        except PurchasePermissionDeniedError:
                            has_override = False
                    self._tol_policy.enforce_over_receipt(
                        ordered, total_received, self._tolerance,
                        has_override_permission=has_override)
                    gr.add_line(GoodsReceiptLine.create(
                        product_id, ordered, received, accepted,
                        purchase_order_line_id=po_line.id if po_line else None, **extra))
                    if raw.get("discrepancy_type"):
                        gr.add_discrepancy(ReceiptDiscrepancy.create(
                            DiscrepancyType(raw["discrepancy_type"]), ordered, received,
                            raw.get("discrepancy_reason", "")))
                    elif received > accepted:
                        # Lo rechazado NO entra al inventario y queda como diferencia.
                        gr.add_discrepancy(ReceiptDiscrepancy.create(
                            DiscrepancyType.QUALITY_FAILURE, received, accepted,
                            raw.get("rejection_reason") or "Rechazado en recepción"))
                    if po_line is not None:
                        # Acumulado: varias líneas recibidas (lotes distintos) para la
                        # misma línea de OC. Antes la última pisaba a las anteriores.
                        received_by_line[po_line.id] = total_received
                        po_line.accepted_quantity += accepted
                        po_line.rejected_quantity += received - accepted
                gr.complete()
                po.register_receipt(received_by_line)
            except ProcurementDomainError as exc:
                code = ("SEGREGATION" if "Separación" in str(exc)
                        else "OVER_TOLERANCE" if "tolerancia" in str(exc).lower()
                        else "INVALID_STATE")
                return ProcurementResult.fail(str(exc), code, operation_id=operation_id)
            uow.receipts.save(gr)
            uow.receipts.set_operation_id(gr.id, operation_id)
            uow.orders.save(po)
            uow.audit.record(action=ProcurementEvents.GOODS_RECEIPT_COMPLETED,
                             actor_user_id=actor_user_id, document_id=gr.id,
                             operation_id=operation_id, branch_id=po.branch_id)
            _emit(uow, ProcurementEvents.GOODS_RECEIPT_COMPLETED, document_id=gr.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  supplier_id=po.supplier_id, branch_id=po.branch_id,
                  purchase_order_id=po.id, warehouse_id=po.warehouse_id,
                  shipment_id=shipment_id, goods_receipt_id=gr.id,
                  document_number=gr.document_number,
                  inventory_lines=[_receipt_inventory_line(
                      ln, lines_by_id.get(ln.purchase_order_line_id)
                      or lines_by_product.get(ln.product_id)) for ln in gr.lines])
            if gr.discrepancies:
                _emit(uow, ProcurementEvents.GOODS_RECEIPT_DISCREPANCY, document_id=gr.id,
                      operation_id=operation_id, actor_user_id=actor_user_id,
                      count=len(gr.discrepancies))
        return ProcurementResult.ok("Recepción registrada", entity_id=gr.id,
                                    operation_id=operation_id,
                                    order_status=po.status.value,
                                    document_number=gr.document_number,
                                    accepted=str(gr.total_accepted()))

    def _profile_problem(self, product_id: str, accepted: Decimal, extra: dict, *,
                         label: str) -> str | None:
        """§25: lo que el producto exige capturar al recibir. Sin catálogo (pruebas
        aisladas) no se exige nada."""
        profile_of = getattr(self._catalog, "purchase_profile", None)
        if profile_of is None or accepted <= 0:
            return None
        profile = profile_of(product_id)
        if profile is None:
            return None
        name = profile.name or label or "El producto"
        if profile.lot_controlled and not extra.get("lot"):
            return f"{name} requiere lote al recibir"
        if profile.expiration_controlled and not extra.get("expiration"):
            return f"{name} requiere caducidad al recibir"
        if profile.catch_weight and not extra.get("net_weight"):
            return f"{name} se maneja por peso variable: captura el peso real"
        if getattr(profile, "temperature_tracked", False) and extra.get("temperature") is None:
            return f"{name} requiere temperatura al recibir"
        return None


class ReverseGoodsReceiptUseCase:
    """Reverses a completed receipt against a purchase order (data-entry error,
    not a supplier-facing return — that's PurchaseReturn). Reopens the order's
    received/accepted/rejected quantities by exactly what this receipt added and
    emits GOODS_RECEIPT_REVERSED so Inventory can compensate the posted movement
    (see GoodsReceiptReversedHandler). Direct-purchase receipts are reversed via
    ReverseDirectPurchaseUseCase instead, not here."""

    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, goods_receipt_id: str,
                operation_id: str, reason: str) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RECEIPT_REVERSE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        if not reason or not reason.strip():
            return ProcurementResult.fail("El reverso requiere un motivo", "VALIDATION",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            gr = uow.receipts.get(goods_receipt_id)
            if gr is None:
                return ProcurementResult.fail("Recepción inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            if gr.status == "REVERSED":
                return ProcurementResult.ok("Recepción ya reversada", entity_id=gr.id,
                                            operation_id=operation_id, status=gr.status)
            if not gr.purchase_order_id:
                return ProcurementResult.fail(
                    "Esta recepción pertenece a una compra directa; reviértela desde ahí",
                    "NOT_A_PURCHASE_ORDER_RECEIPT", operation_id=operation_id)
            po = uow.orders.get(gr.purchase_order_id)
            if po is None:
                return ProcurementResult.fail("Orden inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            lines_by_product = {ln.product_id: ln for ln in po.lines}
            try:
                quantities: dict[str, Decimal] = {}
                for gr_line in gr.lines:
                    po_line = lines_by_product.get(gr_line.product_id)
                    if po_line is None:
                        continue
                    po_line.accepted_quantity = max(
                        Decimal("0"), po_line.accepted_quantity - gr_line.accepted_quantity)
                    po_line.rejected_quantity = max(
                        Decimal("0"), po_line.rejected_quantity - gr_line.rejected_quantity)
                    quantities[po_line.id] = gr_line.received_quantity
                po.unregister_receipt(quantities)
                gr.reverse()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            uow.receipts.save(gr)
            uow.orders.save(po)
            uow.audit.record(action=ProcurementEvents.GOODS_RECEIPT_REVERSED,
                             actor_user_id=actor_user_id, document_id=gr.id,
                             reason=reason.strip(), operation_id=operation_id,
                             branch_id=gr.branch_id)
            _emit(uow, ProcurementEvents.GOODS_RECEIPT_REVERSED, document_id=gr.id,
                  operation_id=operation_id, actor_user_id=actor_user_id,
                  goods_receipt_id=gr.id, purchase_order_id=po.id,
                  reason=reason.strip())
        return ProcurementResult.ok("Recepción reversada", entity_id=gr.id,
                                    operation_id=operation_id, status=gr.status,
                                    order_status=po.status.value)


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


def _receipt_inventory_line(receipt_line, order_line) -> dict:
    """Lo que entra a inventario por una línea recibida: cantidad ACEPTADA
    convertida a la unidad de inventario y costo por esa unidad. Antes se mandaba
    la cantidad en unidad de compra y sin costo (2 cajas de 20 kg entraban como 2
    kg y el costeo ignoraba la recepción)."""
    quantity = receipt_line.inventory_quantity()
    line = {"product_id": receipt_line.product_id}
    if order_line is None:
        line["quantity"] = str(quantity)
        return _with_traceability(line, receipt_line)
    factor = order_line.conversion_factor or Decimal("1")
    weight = accepted_weight(receipt_line)
    if order_line.priced_by_weight() and weight:
        # Se paga el PESO REAL aceptado a $/kg; entra el peso si la unidad de
        # inventario es de peso, si no las piezas, con el costo repartido.
        inventory_quantity = weight if order_line.inventory_by_weight else quantity * factor
        amount = weight * order_line.unit_price.amount
        line["quantity"] = str(inventory_quantity)
        line["unit_cost"] = str(amount / inventory_quantity if inventory_quantity else
                                order_line.unit_price.amount)
        if order_line.inventory_unit:
            line["inventory_unit"] = order_line.inventory_unit
        return _with_traceability(line, receipt_line)
    line["quantity"] = str(quantity * factor)
    line["unit_cost"] = str(inventory_unit_cost(order_line.unit_price.amount, factor))
    if order_line.inventory_unit:
        line["inventory_unit"] = order_line.inventory_unit
    return _with_traceability(line, receipt_line)


def accepted_weight(receipt_line) -> Decimal | None:
    """Peso real de lo ACEPTADO: el peso recibido en proporción a lo aceptado."""
    if not receipt_line.net_weight or not receipt_line.received_quantity:
        return None
    return (receipt_line.net_weight * receipt_line.accepted_quantity
            / receipt_line.received_quantity)


def _with_traceability(line: dict, receipt_line) -> dict:
    """Lote, caducidad y peso real viajan a Inventario (§29): sin esto el lote se
    capturaba en la recepción y el inventario lo ignoraba."""
    if receipt_line.lot:
        line["lot"] = receipt_line.lot
    if receipt_line.expiration:
        line["expiration"] = receipt_line.expiration.isoformat()
    if receipt_line.net_weight is not None:
        line["weight"] = str(receipt_line.net_weight)
    if receipt_line.temperature is not None:
        line["temperature"] = str(receipt_line.temperature)
    return line


def _requisition_fully_covered(requisition, orders, new_order) -> bool:
    """¿Las órdenes de la solicitud (más la nueva) cubren todo lo pedido?

    Se compara en unidad de INVENTARIO (cantidad ordenada × factor) contra la
    cantidad de la solicitud, que se captura en unidad base. Las órdenes
    rechazadas no cuentan."""
    by_id = {order.id: order for order in orders}
    by_id[new_order.id] = new_order        # ya guardada: no contarla dos veces
    ordered: dict[str, Decimal] = {}
    for order in by_id.values():
        if order.status is PurchaseOrderStatus.REJECTED:
            continue
        for line in order.lines:
            ordered[line.product_id] = (ordered.get(line.product_id, Decimal("0"))
                                        + line.ordered_quantity * (line.conversion_factor
                                                                   or Decimal("1")))
    requested: dict[str, Decimal] = {}
    for line in requisition.lines:
        requested[line.product_id] = requested.get(line.product_id, Decimal("0")) + line.quantity
    return all(ordered.get(pid, Decimal("0")) >= qty for pid, qty in requested.items())


_DELIVERY_METHODS = {"SUPPLIER_DELIVERY", "SUPPLIER_PICKUP"}
_HEADER_KEYS = ("exchange_rate", "required_date", "promised_date", "delivery_method",
                "delivery_address", "cost_center", "project_reference",
                "contract_reference", "notes", "origin_supplier_address_id")


def _order_header(raw: dict, currency_code: str) -> tuple[dict, str | None]:
    """Encabezado enterprise (§23) normalizado: textos recortados, vacíos → None.
    Moneda distinta a MXN exige tipo de cambio > 0."""
    unknown = set(raw) - set(_HEADER_KEYS)
    if unknown:
        return {}, f"Campo de orden desconocido: {', '.join(sorted(unknown))}"
    header = {}
    for key in _HEADER_KEYS:
        value = raw.get(key)
        value = value.strip() if isinstance(value, str) else value
        header[key] = value if value not in ("", None) else None
    if header["delivery_method"] and header["delivery_method"] not in _DELIVERY_METHODS:
        return {}, "Forma de entrega no válida"
    rate = header["exchange_rate"]
    if rate is not None:
        try:
            rate = Decimal(str(rate))
        except ArithmeticError:
            return {}, "Tipo de cambio no válido"
        if rate <= 0:
            return {}, "El tipo de cambio debe ser mayor a cero"
        header["exchange_rate"] = rate
    if currency_code != "MXN" and header["exchange_rate"] is None:
        return {}, f"Una orden en {currency_code} requiere tipo de cambio"
    return header, None


def _receipt_capture(raw: dict) -> dict:
    """Lote, caducidad, temperatura, peso real y piezas capturados al recibir."""
    from datetime import date as _date
    capture = {}
    lot = (raw.get("lot") or raw.get("lot_number") or "").strip()
    if lot:
        capture["lot"] = lot
    expiration = raw.get("expiration") or raw.get("expiration_date")
    if expiration:
        capture["expiration"] = (expiration if isinstance(expiration, _date)
                                 else _date.fromisoformat(str(expiration)))
    for key in ("temperature", "net_weight"):
        if raw.get(key) not in (None, ""):
            capture[key] = Decimal(str(raw[key]))
    if raw.get("piece_count") not in (None, ""):
        capture["piece_count"] = int(raw["piece_count"])
    return capture
