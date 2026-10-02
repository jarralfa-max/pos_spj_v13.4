"""Direct-purchase application flow (§12, §56, §64) — the fast route executed
INSIDE Compras (never the POS).

Route: create draft → [hot authorization if over limit] → confirm → (immediate
receipt → inventory of accepted qty) → financial treatment (immediate payment
request / supplier-credit payable) → reversible.

Every use case:
- re-validates its granular permission via the injected RBAC checker,
- runs inside a single ProcurementUnitOfWork (atomic; rollback on any error),
- records audit and enqueues the canonical event to the transactional outbox
  (dispatched only post-commit),
- is idempotent where repetition must not duplicate state (operation_id).

Immediate payment NEVER draws from the POS operative cash (ImmediatePaymentPolicy).
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.product_master_rules import (
    fraction_problem,
    product_problem,
    units_from_product_master,
    warehouse_problem,
)
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.entities import (
    DirectPurchase,
    DirectPurchaseLine,
    GoodsReceipt,
    GoodsReceiptLine,
    PurchasePaymentInstruction,
)
from backend.domain.procurement.enums import (
    DirectPurchaseMode,
    DocumentStatus,
    PaymentCondition,
    PaymentSource,
    PurchaseNature,
    DEFERRED_FULFILLMENT,
    FulfillmentMode,
)
from backend.domain.procurement.events import ProcurementEvents, build_event_payload
from backend.domain.procurement.exceptions import (
    ProcurementDomainError,
    PurchasePermissionDeniedError,
)
from backend.domain.procurement.policies import (
    ImmediatePaymentPolicy,
    LimitEvaluation,
    SegregationOfDutiesPolicy,
    SupplierEligibilityPolicy,
    UserPurchaseLimitPolicy,
)
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


def _nature_subtotals(lines) -> dict[str, str]:
    """Pre-tax subtotal per purchase_nature — same shape as
    `supplier_invoice_use_cases.py::_nature_subtotals`, so the Finance-side
    immediate-payment bridge can recognize the right debit account
    (Inventario/Gasto/Activo) instead of guessing one."""
    from decimal import Decimal
    totals: dict[str, Decimal] = {}
    for line in lines:
        nature = line.purchase_nature.value
        totals[nature] = totals.get(nature, Decimal("0")) + line.line_subtotal().amount
    return {nature: str(amount) for nature, amount in totals.items()}


def _eligibility_problem(dp, *, product_catalog=None,
                         warehouse_directory=None) -> tuple[str, str] | None:
    """`(código, mensaje)` si la compra no se puede registrar tal como está.

    Medido el 2026-09-18 sobre una copia de la base real: la compra rápida se
    creaba Y CONFIRMABA con un producto EN REVISIÓN (no activo) y con el almacén
    de OTRA sucursal, y la mercancía entraba al inventario igual. Se valida al
    crear y OTRA VEZ al confirmar: entre el borrador y la confirmación el
    producto puede haberse retirado o el almacén desactivado.

    Los puertos son opcionales para las pruebas aisladas; la composición real
    (`direct_purchase_routes.py`) los inyecta siempre.
    """
    problema = warehouse_problem(warehouse_directory, dp.branch_id, dp.warehouse_id)
    if problema is not None:
        return problema
    for line in dp.lines:
        problema = product_problem(product_catalog, line.product_id,
                                   line.description or line.product_id)
        if problema is not None:
            return problema
    return None


class _BaseDirectPurchaseUseCase:
    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def _emit_received(self, uow: ProcurementUnitOfWork, dp: DirectPurchase, receipt_id: str,
                       operation_id: str, actor_user_id: str,
                       inventory_lines: list[dict] | None = None) -> None:
        """Entrada al inventario de lo recibido (recepción inmediata o posterior).
        ``inventory_lines`` = lo ACEPTADO al contar (con lote, caducidad y peso);
        sin ellas entra la compra completa."""
        self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_RECEIVED,
                   document_id=dp.id, operation_id=operation_id,
                   actor_user_id=actor_user_id, supplier_id=dp.supplier_id,
                   branch_id=dp.branch_id, goods_receipt_id=receipt_id,
                   warehouse_id=dp.warehouse_id,
                   source_channel=dp.source_channel.value,
                   document_number=dp.document_number,
                   supplier_ref=dp.supplier_id,
                   inventory_lines=inventory_lines if inventory_lines is not None else [
                       {"product_id": ln.product_id,
                        "quantity": str(ln.inventory_quantity()),
                        "unit_cost": str(_inventory_unit_cost(ln)),
                        "inventory_unit": ln.inventory_unit}
                       for ln in dp.lines])

    def _emit(self, uow: ProcurementUnitOfWork, event_name: str, *, document_id: str,
              operation_id: str, actor_user_id: str | None = None, **extra) -> None:
        payload = build_event_payload(
            event_name, operation_id=operation_id, document_id=document_id,
            user_id=actor_user_id, **extra)
        uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                           payload_json=json.dumps(payload), operation_id=operation_id)


class CreateDirectPurchaseUseCase(_BaseDirectPurchaseUseCase):
    """Creates a direct-purchase draft with its lines and evaluates the user limit.

    If the amount is within the user limit the draft is ready to confirm; if it is
    over the approval threshold or the hard cap it is left PENDING_AUTHORIZATION so
    a second user can authorize it in place before confirmation.
    """

    def __init__(self, authorization=None, supplier_directory=None, *,
                 product_catalog=None, warehouse_directory=None,
                 supplier_origins=None) -> None:
        super().__init__(authorization)
        self._supplier_directory = supplier_directory
        self._product_catalog = product_catalog
        self._warehouse_directory = warehouse_directory
        #: `SupplierOriginQueryService`: bodegas del proveedor para recolección.
        self._supplier_origins = supplier_origins
        self._limits = UserPurchaseLimitPolicy()
        self._supplier = SupplierEligibilityPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str,
                supplier_id: str, branch_id: str, warehouse_id: str,
                lines: list[dict], mode: str = DirectPurchaseMode.DIRECT_WITH_IMMEDIATE_RECEIPT.value,
                payment_condition: str = PaymentCondition.IMMEDIATE_PAYMENT.value,
                currency_code: str = "MXN", supplier_active: bool = True,
                supplier_purchasing_blocked: bool = False,
                terminal_id: str | None = None,
                source_requisition_id: str | None = None,
                fulfillment_mode: str | None = None,
                origin_supplier_address_id: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.DIRECT_CREATE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            existing = uow.direct_purchases.get_by_operation(operation_id)
            if existing is not None:
                return ProcurementResult.ok("Compra directa ya registrada",
                                            entity_id=existing.id, operation_id=operation_id,
                                            status=existing.status.value,
                                            already_registered=True,
                                            document_number=existing.document_number)
            try:
                if self._supplier_directory is not None:
                    self._supplier_directory.require_eligible(supplier_id)
                self._supplier.enforce(active=supplier_active,
                                       purchasing_blocked=supplier_purchasing_blocked)
                if not uow.limits.branch_allows_direct(branch_id, currency_code):
                    return ProcurementResult.fail(
                        "La sucursal no tiene habilitada la compra directa",
                        "BRANCH_NOT_ALLOWED", operation_id=operation_id)
                mode, fulfillment, problema = _resolve_fulfillment(mode, fulfillment_mode)
                if problema is not None:
                    return ProcurementResult.fail(problema, "VALIDATION",
                                                  operation_id=operation_id)
                origin, problema = self._pickup_origin(
                    fulfillment, supplier_id, origin_supplier_address_id)
                if problema is not None:
                    return ProcurementResult.fail(problema, "ORIGIN_REQUIRED",
                                                  operation_id=operation_id)
                document_number = uow.sequences.next_number("CD", _year())
                dp = DirectPurchase.create(
                    document_number, supplier_id, branch_id, warehouse_id,
                    DirectPurchaseMode(mode), PaymentCondition(payment_condition),
                    created_by_user_id=actor_user_id, currency_code=currency_code)
                dp.fulfillment_mode = fulfillment
                dp.origin_supplier_address_id, dp.origin_address_snapshot = origin
                if source_requisition_id:
                    requisition = uow.requisitions.get(source_requisition_id)
                    if requisition is None or requisition.status.value != "APPROVED":
                        return ProcurementResult.fail(
                            "La compra directa requiere una solicitud aprobada",
                            "INVALID_REQUISITION", operation_id=operation_id)
                    dp.source_requisition_id = source_requisition_id
                for raw in lines:
                    resolved, problema = units_from_product_master(raw, self._product_catalog)
                    if problema is not None:
                        return ProcurementResult.fail(problema[1], problema[0],
                                                      operation_id=operation_id)
                    dp.add_line(_line_from_dict(resolved, currency_code))
                if not dp.lines:
                    return ProcurementResult.fail("La compra requiere al menos una línea",
                                                  "EMPTY", operation_id=operation_id)
                problema = _eligibility_problem(
                    dp, product_catalog=self._product_catalog,
                    warehouse_directory=self._warehouse_directory)
                if problema is not None:
                    return ProcurementResult.fail(problema[1], problema[0],
                                                  operation_id=operation_id)
            except (ProcurementDomainError, ValueError) as exc:
                return ProcurementResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

            user_limit = uow.limits.get_user_limit(actor_user_id, currency_code)
            evaluation = self._limits.evaluate(dp.total(), user_limit)
            requires_auth = evaluation is not LimitEvaluation.WITHIN
            if requires_auth:
                dp.request_authorization(
                    "Supera el límite del usuario" if evaluation is LimitEvaluation.EXCEEDS
                    else "Supera el umbral de autorización")

            uow.direct_purchases.save(dp)
            uow.direct_purchases.set_operation_id(dp.id, operation_id)
            uow.audit.record(action=ProcurementEvents.DIRECT_PURCHASE_DRAFTED,
                             actor_user_id=actor_user_id, document_id=dp.id,
                             after_json=json.dumps({"total": str(dp.total().amount),
                                                    "lines": len(dp.lines)}),
                             reason="alta compra directa", operation_id=operation_id,
                             branch_id=branch_id, terminal_id=terminal_id,
                             source_channel=dp.source_channel.value)
            self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_DRAFTED, document_id=dp.id,
                       operation_id=operation_id, actor_user_id=actor_user_id,
                       supplier_id=supplier_id, branch_id=branch_id,
                       document_number=dp.document_number)
            if requires_auth:
                self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_AUTHORIZATION_REQUESTED,
                           document_id=dp.id, operation_id=operation_id,
                           actor_user_id=actor_user_id, supplier_id=supplier_id,
                           branch_id=branch_id, amount=str(dp.total().amount))
        return ProcurementResult.ok(
            "Compra directa creada", entity_id=dp.id, operation_id=operation_id,
            status=dp.status.value, requires_authorization=requires_auth,
            total=str(dp.total().amount), document_number=dp.document_number)


    def _pickup_origin(self, fulfillment: str, supplier_id: str, address_id: str | None
                       ) -> tuple[tuple[str | None, str | None], str | None]:
        """Recolección en proveedor: la bodega es obligatoria y debe ser DEL
        proveedor; se guarda con la foto del domicilio (mismo criterio que la OC)."""
        if fulfillment != FulfillmentMode.SUPPLIER_PICKUP.value:
            return (None, None), None
        if not address_id:
            return (None, None), "Para recolección en proveedor elige la bodega de origen"
        if self._supplier_origins is None:
            return (address_id, None), None
        origin = self._supplier_origins.origin_location(supplier_id, address_id)
        if origin is None:
            return (None, None), ("La bodega o punto de recolección no pertenece al "
                                  "proveedor elegido")
        return (address_id, json.dumps(origin["snapshot"], ensure_ascii=False)), None


def _resolve_fulfillment(mode: str, fulfillment: str | None
                         ) -> tuple[str, str, str | None]:
    """(modo, surtido, problema). El surtido decide si la recepción es
    inmediata o queda pendiente; sin surtido se deduce del modo (compatibilidad).
    Servicios y gastos no tienen surtido logístico."""
    goods = {DirectPurchaseMode.DIRECT_WITH_IMMEDIATE_RECEIPT.value,
             DirectPurchaseMode.DIRECT_WITH_PENDING_RECEIPT.value}
    if mode and mode not in goods:
        return mode, "", None
    mode = mode or DirectPurchaseMode.DIRECT_WITH_IMMEDIATE_RECEIPT.value
    if not fulfillment:
        return mode, (FulfillmentMode.IMMEDIATE_RECEIPT.value
                      if mode == DirectPurchaseMode.DIRECT_WITH_IMMEDIATE_RECEIPT.value
                      else FulfillmentMode.LATER_RECEIPT.value), None
    try:
        chosen = FulfillmentMode(fulfillment)
    except ValueError:
        return mode, "", f"Forma de surtido no válida: {fulfillment}"
    resolved = (DirectPurchaseMode.DIRECT_WITH_PENDING_RECEIPT.value
                if chosen in DEFERRED_FULFILLMENT
                else DirectPurchaseMode.DIRECT_WITH_IMMEDIATE_RECEIPT.value)
    return resolved, chosen.value, None


class AuthorizeDirectPurchaseUseCase(_BaseDirectPurchaseUseCase):
    """Hot authorization (§64): a second user with the permission authorizes an
    over-limit direct purchase in place; the exception is always logged and the
    creator can never self-authorize an over-limit purchase (segregation)."""

    def __init__(self, authorization=None) -> None:
        super().__init__(authorization)
        self._sod = SegregationOfDutiesPolicy()

    def execute(self, connection, *, authorizer_user_id: str, direct_purchase_id: str,
                operation_id: str, reason: str,
                terminal_id: str | None = None) -> ProcurementResult:
        try:
            self._auth.authorize_exception(authorizer_user_id,
                                           PurchasePermissions.OVERRIDE_FINANCIAL_LIMIT)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            dp = uow.direct_purchases.get(direct_purchase_id)
            if dp is None:
                return ProcurementResult.fail("Compra directa inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            if dp.status is not DocumentStatus.PENDING_AUTHORIZATION:
                return ProcurementResult.ok("La compra no requiere autorización",
                                            entity_id=dp.id, operation_id=operation_id,
                                            status=dp.status.value)
            if not reason or not reason.strip():
                return ProcurementResult.fail("La autorización requiere un motivo",
                                              "VALIDATION", operation_id=operation_id)
            try:
                self._sod.enforce_distinct(
                    dp.created_by_user_id, authorizer_user_id,
                    "quien crea una compra elevada no la autoriza")
                dp.authorize(authorizer_user_id)
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "SEGREGATION", operation_id=operation_id)

            uow.direct_purchases.save(dp)
            log_id = uow.authorization_log.record(
                operation_id=operation_id,
                permission_code=PurchasePermissions.OVERRIDE_FINANCIAL_LIMIT,
                requested_by_user_id=dp.created_by_user_id or "",
                authorized_by_user_id=authorizer_user_id, reason=reason.strip(),
                amount=dp.total().amount, document_id=dp.id, terminal_id=terminal_id)
            uow.direct_purchases.record_authorization(
                direct_purchase_id=dp.id, requested_by_user_id=dp.created_by_user_id or "",
                authorized_by_user_id=authorizer_user_id,
                permission_code=PurchasePermissions.OVERRIDE_FINANCIAL_LIMIT,
                reason=reason.strip(), amount=dp.total().amount,
                currency_code=dp.currency_code, terminal_id=terminal_id,
                operation_id=operation_id, authorization_id=log_id, created_at=dp.updated_at)
            uow.audit.record(action=ProcurementEvents.DIRECT_PURCHASE_AUTHORIZED,
                             actor_user_id=authorizer_user_id, authorized_by=authorizer_user_id,
                             document_id=dp.id, reason=reason.strip(),
                             operation_id=operation_id, terminal_id=terminal_id)
            self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_AUTHORIZED, document_id=dp.id,
                       operation_id=operation_id, actor_user_id=authorizer_user_id,
                       authorized_by=authorizer_user_id, amount=str(dp.total().amount))
        return ProcurementResult.ok("Compra directa autorizada", entity_id=dp.id,
                                    operation_id=operation_id, status=dp.status.value)


class ConfirmDirectPurchaseUseCase(_BaseDirectPurchaseUseCase):
    """Confirms an (authorized) draft. On immediate-receipt mode it also generates
    the goods receipt and emits the inventory-entry event for the ACCEPTED quantity
    only; it then requests the financial treatment (immediate payment from an
    authorized source — never POS cash — or a supplier-credit payable)."""

    def __init__(self, authorization=None, *, supplier_directory=None,
                 product_catalog=None, warehouse_directory=None,
                 payment_booking=None) -> None:
        super().__init__(authorization)
        self._payment = ImmediatePaymentPolicy()
        self._supplier_directory = supplier_directory
        self._product_catalog = product_catalog
        self._warehouse_directory = warehouse_directory
        #: `PaymentSourceBookingPort`. Sin él, un pago de contado que Finanzas
        #: no sabe asentar se confirmaba igual: el dinero salía sin asiento.
        self._payment_booking = payment_booking

    def execute(self, connection, *, actor_user_id: str, direct_purchase_id: str,
                operation_id: str, payment_source: str | None = None,
                terminal_id: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.DIRECT_CONFIRM)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            dp = uow.direct_purchases.get(direct_purchase_id)
            if dp is None:
                return ProcurementResult.fail("Compra directa inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            if dp.status is DocumentStatus.CONFIRMED or dp.status is DocumentStatus.RECEIVED:
                return ProcurementResult.ok("Compra ya confirmada", entity_id=dp.id,
                                            operation_id=operation_id, status=dp.status.value,
                                            already_confirmed=True)
            if dp.status is DocumentStatus.PENDING_AUTHORIZATION:
                return ProcurementResult.fail(
                    "La compra requiere autorización antes de confirmar",
                    "AUTHORIZATION_REQUIRED", operation_id=operation_id)
            # financial guard: immediate payment must not come from POS cash
            if dp.payment_condition is PaymentCondition.IMMEDIATE_PAYMENT:
                source = payment_source or ""
                try:
                    self._payment.enforce_source(source)
                except ProcurementDomainError as exc:
                    return ProcurementResult.fail(str(exc), "INVALID_PAYMENT_SOURCE",
                                                  operation_id=operation_id)
                # Y además tiene que poder ASENTARSE. Antes esto sólo lo sabía
                # el puente contable, después de confirmar: registraba una
                # advertencia y la compra quedaba pagada sin asiento (§11).
                if self._payment_booking is not None:
                    problema = self._payment_booking.booking_problem(source, dp.branch_id)
                    if problema:
                        return ProcurementResult.fail(
                            f"No se puede confirmar el pago de contado: {problema}.",
                            "PAYMENT_NOT_BOOKABLE", operation_id=operation_id)
            # Revalidar: el proveedor pudo bloquearse, o el producto retirarse,
            # desde que se capturó el borrador.
            if self._supplier_directory is not None:
                try:
                    self._supplier_directory.require_eligible(dp.supplier_id)
                except ProcurementDomainError as exc:
                    return ProcurementResult.fail(str(exc), "SUPPLIER_NOT_ELIGIBLE",
                                                  operation_id=operation_id)
            problema_compra = _eligibility_problem(
                dp, product_catalog=self._product_catalog,
                warehouse_directory=self._warehouse_directory)
            if problema_compra is not None:
                return ProcurementResult.fail(problema_compra[1], problema_compra[0],
                                              operation_id=operation_id)
            try:
                dp.confirm()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            if dp.payment_condition is PaymentCondition.IMMEDIATE_PAYMENT:
                # La fuente con que se pagó queda EN el documento (columna
                # `direct_purchases.payment_source`). Antes sólo viajaba en el
                # evento PURCHASE_PAYMENT_REQUESTED y el documento la perdía.
                dp.payment_instruction = PurchasePaymentInstruction.create(
                    PaymentSource(payment_source), dp.total())

            receipt_id = None
            if dp.is_immediate_receipt():
                gr = _build_receipt(dp, actor_user_id, uow.sequences.next_number("REC", _year()))
                gr.complete()
                dp.mark_received()
                uow.receipts.save(gr)
                uow.direct_purchases.link_receipt(dp.id, gr.id)
                receipt_id = gr.id
            uow.direct_purchases.save(dp)
            if dp.source_requisition_id:
                source_requisition = uow.requisitions.get(dp.source_requisition_id)
                if source_requisition is not None:
                    source_requisition.mark_sourced()
                    uow.requisitions.save(source_requisition)

            uow.audit.record(action=ProcurementEvents.DIRECT_PURCHASE_CONFIRMED,
                             actor_user_id=actor_user_id, document_id=dp.id,
                             reason="confirmación", operation_id=operation_id,
                             branch_id=dp.branch_id, terminal_id=terminal_id)
            self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_CONFIRMED, document_id=dp.id,
                       operation_id=operation_id, actor_user_id=actor_user_id,
                       supplier_id=dp.supplier_id, branch_id=dp.branch_id,
                       total=str(dp.total().amount))
            if receipt_id is not None:
                self._emit_received(uow, dp, receipt_id, operation_id, actor_user_id)
            else:
                self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_RECEIPT_PENDING,
                           document_id=dp.id, operation_id=operation_id,
                           actor_user_id=actor_user_id, supplier_id=dp.supplier_id)
            # financial treatment
            if dp.payment_condition is PaymentCondition.IMMEDIATE_PAYMENT:
                self._emit(uow, ProcurementEvents.PURCHASE_PAYMENT_REQUESTED,
                           document_id=dp.id, document_number=dp.document_number,
                           operation_id=operation_id,
                           actor_user_id=actor_user_id, supplier_id=dp.supplier_id,
                           branch_id=dp.branch_id,
                           amount=str(dp.total().amount),
                           currency_code=dp.total().currency_code,
                           payment_source=payment_source,
                           nature_subtotals=_nature_subtotals(dp.lines),
                           tax_total=str(dp.tax_total().amount))
            # Supplier credit records the commercial commitment only. The final
            # CxP is requested exclusively after invoice validation and matching.
        return ProcurementResult.ok("Compra directa confirmada", entity_id=dp.id,
                                    operation_id=operation_id, status=dp.status.value,
                                    goods_receipt_id=receipt_id)


class ReceiveDirectPurchaseUseCase(_BaseDirectPurchaseUseCase):
    """Recepción POSTERIOR de una compra rápida «con recepción pendiente».

    No existía: el modo se podía elegir y confirmar, pero la mercancía nunca
    podía recibirse. Sin recepción la compra no entraba al inventario, su
    factura conciliaba «sin recepción» y, a crédito, jamás generaba la cuenta
    por pagar (§34: compra → recepción → factura → conciliación → CxP).
    Recibe la compra completa, igual que la recepción inmediata.
    """

    def __init__(self, authorization=None, *, warehouse_directory=None,
                 product_catalog=None) -> None:
        super().__init__(authorization)
        self._warehouse_directory = warehouse_directory
        self._product_catalog = product_catalog

    def execute(self, connection, *, actor_user_id: str, direct_purchase_id: str,
                operation_id: str, receipt_lines: list[dict] | None = None,
                shipment_id: str | None = None) -> ProcurementResult:
        """Sin ``receipt_lines`` se recibe la compra completa. Con ellas (lo
        CONTADO al llegar un embarque de recolección), sólo lo ACEPTADO entra al
        inventario, con su lote, caducidad y peso; lo rechazado queda registrado."""
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RECEIPT_CREATE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            existing = uow.receipts.get_by_operation(operation_id)
            if existing is not None:
                return ProcurementResult.ok("Recepción ya registrada", entity_id=direct_purchase_id,
                                            operation_id=operation_id, status="RECEIVED",
                                            goods_receipt_id=existing.id)
            dp = uow.direct_purchases.get(direct_purchase_id)
            if dp is None:
                return ProcurementResult.fail("Compra directa inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            if dp.status is DocumentStatus.RECEIVED:
                return ProcurementResult.fail("La compra ya se recibió", "INVALID_STATE",
                                              operation_id=operation_id)
            if dp.status is not DocumentStatus.CONFIRMED or dp.is_immediate_receipt():
                return ProcurementResult.fail(
                    "Sólo se recibe una compra confirmada con recepción pendiente",
                    "INVALID_STATE", operation_id=operation_id)
            problema = warehouse_problem(self._warehouse_directory, dp.branch_id,
                                         dp.warehouse_id)
            if problema is not None:
                return ProcurementResult.fail(problema[1], problema[0],
                                              operation_id=operation_id)
            number = uow.sequences.next_number("REC", _year())
            inventory_lines = None
            if receipt_lines is None:
                gr = _build_receipt(dp, actor_user_id, number)
            else:
                lines = {ln.id: ln for ln in dp.lines}
                for raw in receipt_lines:
                    ln = lines.get(raw.get("direct_purchase_line_id")
                                   or raw.get("purchase_order_line_id") or "")
                    problema = None if ln is None else fraction_problem(
                        self._product_catalog, ln.product_id, ln.purchase_unit,
                        (raw.get("received_quantity"), raw.get("accepted_quantity")),
                        ln.description)
                    if problema is not None:
                        return ProcurementResult.fail(problema, "VALIDATION",
                                                      operation_id=operation_id)
                try:
                    gr, inventory_lines = _counted_receipt(dp, actor_user_id, number,
                                                           receipt_lines)
                except (ProcurementDomainError, ValueError, ArithmeticError) as exc:
                    return ProcurementResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            gr.shipment_id = shipment_id
            gr.complete()
            dp.mark_received()
            uow.receipts.save(gr)
            uow.receipts.set_operation_id(gr.id, operation_id)
            uow.direct_purchases.link_receipt(dp.id, gr.id)
            uow.direct_purchases.save(dp)
            uow.audit.record(action=ProcurementEvents.DIRECT_PURCHASE_RECEIVED,
                             actor_user_id=actor_user_id, document_id=dp.id,
                             reason="recepción posterior", operation_id=operation_id,
                             branch_id=dp.branch_id)
            self._emit_received(uow, dp, gr.id, operation_id, actor_user_id,
                                inventory_lines=inventory_lines)
        return ProcurementResult.ok("Mercancía recibida", entity_id=dp.id,
                                    operation_id=operation_id, status=dp.status.value,
                                    goods_receipt_id=gr.id,
                                    document_number=gr.document_number)


class ReverseDirectPurchaseUseCase(_BaseDirectPurchaseUseCase):
    """Reverses a confirmed/received direct purchase (§ reverse). Emits the
    compensating inventory/financial events; nothing is physically deleted."""

    def execute(self, connection, *, actor_user_id: str, direct_purchase_id: str,
                operation_id: str, reason: str,
                terminal_id: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.DIRECT_REVERSE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        if not reason or not reason.strip():
            return ProcurementResult.fail("El reverso requiere un motivo", "VALIDATION",
                                          operation_id=operation_id)
        with ProcurementUnitOfWork(connection) as uow:
            dp = uow.direct_purchases.get(direct_purchase_id)
            if dp is None:
                return ProcurementResult.fail("Compra directa inexistente", "NOT_FOUND",
                                              operation_id=operation_id)
            if dp.status is DocumentStatus.REVERSED:
                return ProcurementResult.ok("Compra ya reversada", entity_id=dp.id,
                                            operation_id=operation_id, status=dp.status.value)
            was_received = dp.status is DocumentStatus.RECEIVED
            try:
                dp.reverse()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)
            gr = uow.receipts.get_by_direct_purchase(dp.id)
            if gr is not None and gr.status == "COMPLETED":
                gr.reverse()
                uow.receipts.save(gr)
            uow.direct_purchases.save(dp)
            uow.audit.record(action=ProcurementEvents.DIRECT_PURCHASE_REVERSED,
                             actor_user_id=actor_user_id, document_id=dp.id,
                             reason=reason.strip(), operation_id=operation_id,
                             branch_id=dp.branch_id, terminal_id=terminal_id)
            self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_REVERSED, document_id=dp.id,
                       operation_id=operation_id, actor_user_id=actor_user_id,
                       supplier_id=dp.supplier_id, branch_id=dp.branch_id,
                       reversed_inventory=was_received,
                       warehouse_id=dp.warehouse_id,
                       inventory_lines=[{"product_id": ln.product_id,
                                         "quantity": str(ln.inventory_quantity())}
                                        for ln in dp.lines] if was_received else [])
        return ProcurementResult.ok("Compra directa reversada", entity_id=dp.id,
                                    operation_id=operation_id, status=dp.status.value)


# ── helpers ─────────────────────────────────────────────────────────────────
def _year() -> int:
    from datetime import date
    return date.today().year


def _inventory_unit_cost(line) -> Decimal:
    # Importe entre lo que entra: con peso variable el importe es peso × $/kg y
    # entra el peso real, no cantidad × factor nominal.
    return line.inventory_unit_cost()


def _line_from_dict(raw: dict, currency_code: str) -> DirectPurchaseLine:
    unit_cost = Money(str(raw["unit_cost"]), raw.get("currency_code", currency_code))
    tax = Money(str(raw["tax"]), currency_code) if raw.get("tax") is not None else None
    discount = (Money(str(raw["discount"]), currency_code)
                if raw.get("discount") is not None else None)
    kwargs = {"purchase_unit": raw.get("purchase_unit") or "PZA",
              "purchase_nature": PurchaseNature(
                  raw.get("purchase_nature", PurchaseNature.INVENTORY.value)),
              "inventory_unit": raw.get("inventory_unit") or "PZA",
              "conversion_factor": str(raw.get("conversion_factor") or "1"),
              "destination_branch_id": raw.get("destination_branch_id"),
              "destination_warehouse_id": raw.get("destination_warehouse_id"),
              "net_weight": raw.get("net_weight") or None,
              "pricing_basis": raw.get("pricing_basis") or "",
              "inventory_by_weight": bool(raw.get("inventory_by_weight"))}
    if tax is not None:
        kwargs["tax"] = tax
    if discount is not None:
        kwargs["discount"] = discount
    return DirectPurchaseLine.create(
        raw["product_id"], raw.get("description", ""), str(raw["quantity"]), unit_cost,
        **kwargs)


def _counted_receipt(dp: DirectPurchase, actor_user_id: str, document_number,
                     counted: list[dict]) -> tuple[GoodsReceipt, list[dict]]:
    """Recepción con lo CONTADO (cantidades en unidad de compra, como se
    cargaron). Se guarda en unidad de inventario, igual que la recepción
    inmediata; con peso variable que entra por peso, entra el peso contado."""
    from datetime import date as _date

    lines = {ln.id: ln for ln in dp.lines}
    gr = GoodsReceipt.create(document_number, dp.supplier_id, dp.branch_id, dp.warehouse_id,
                             received_by_user_id=actor_user_id, direct_purchase_id=dp.id)
    inventory_lines = []
    for raw in counted:
        line_id = raw.get("direct_purchase_line_id") or raw.get("purchase_order_line_id")
        ln = lines.get(line_id or "")
        if ln is None:
            raise ValueError("Lo contado no corresponde a una línea de la compra")
        received = Decimal(str(raw.get("received_quantity") or "0"))
        accepted = Decimal(str(raw.get("accepted_quantity", received) or "0"))
        if received <= 0:
            continue
        weight = raw.get("net_weight")
        weight = Decimal(str(weight)) if weight not in (None, "") else None
        if ln.inventory_by_weight and weight:
            received_inventory = weight
        else:
            received_inventory = received * ln.conversion_factor
        accepted_inventory = received_inventory * accepted / received
        expiration = raw.get("expiration")
        receipt_line = GoodsReceiptLine.create(
            ln.product_id, ln.inventory_quantity(), received_inventory, accepted_inventory,
            lot=raw.get("lot") or None,
            expiration=(_date.fromisoformat(str(expiration)) if expiration else None),
            net_weight=weight,
            piece_count=int(raw["piece_count"]) if raw.get("piece_count") not in (None, "")
            else None)
        gr.add_line(receipt_line)
        if accepted_inventory > 0:
            inventory_lines.append({
                "product_id": ln.product_id, "quantity": str(accepted_inventory),
                "unit_cost": str(_inventory_unit_cost(ln)),
                "inventory_unit": ln.inventory_unit, "lot": raw.get("lot") or None,
                "expiration": str(expiration) if expiration else None,
                "weight": str(weight * accepted / received) if weight else 0})
    if not gr.lines:
        raise ValueError("No hay cantidades recibidas")
    return gr, inventory_lines


def _build_receipt(dp: DirectPurchase, actor_user_id: str, document_number) -> GoodsReceipt:
    gr = GoodsReceipt.create(document_number, dp.supplier_id, dp.branch_id, dp.warehouse_id,
                             received_by_user_id=actor_user_id, direct_purchase_id=dp.id)
    for ln in dp.lines:
        qty = ln.inventory_quantity()
        gr.add_line(GoodsReceiptLine.create(ln.product_id, qty, qty, qty,
                                            net_weight=ln.net_weight))
    return gr
