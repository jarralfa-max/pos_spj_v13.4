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
    DocumentStatus,
    PaymentCondition,
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


class _BaseDirectPurchaseUseCase:
    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

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

    def __init__(self, authorization=None) -> None:
        super().__init__(authorization)
        self._limits = UserPurchaseLimitPolicy()
        self._supplier = SupplierEligibilityPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str,
                supplier_id: str, branch_id: str, warehouse_id: str,
                lines: list[dict], mode: str = DirectPurchaseMode.DIRECT_WITH_IMMEDIATE_RECEIPT.value,
                payment_condition: str = PaymentCondition.IMMEDIATE_PAYMENT.value,
                currency_code: str = "MXN", supplier_active: bool = True,
                supplier_purchasing_blocked: bool = False,
                terminal_id: str | None = None) -> ProcurementResult:
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
                                            status=existing.status.value)
            try:
                self._supplier.enforce(active=supplier_active,
                                       purchasing_blocked=supplier_purchasing_blocked)
                if not uow.limits.branch_allows_direct(branch_id, currency_code):
                    return ProcurementResult.fail(
                        "La sucursal no tiene habilitada la compra directa",
                        "BRANCH_NOT_ALLOWED", operation_id=operation_id)
                document_number = uow.sequences.next_number("CD", _year())
                dp = DirectPurchase.create(
                    document_number, supplier_id, branch_id, warehouse_id,
                    DirectPurchaseMode(mode), PaymentCondition(payment_condition),
                    created_by_user_id=actor_user_id, currency_code=currency_code)
                for raw in lines:
                    dp.add_line(_line_from_dict(raw, currency_code))
                if not dp.lines:
                    return ProcurementResult.fail("La compra requiere al menos una línea",
                                                  "EMPTY", operation_id=operation_id)
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

    def __init__(self, authorization=None) -> None:
        super().__init__(authorization)
        self._payment = ImmediatePaymentPolicy()

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
                                            operation_id=operation_id, status=dp.status.value)
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
            try:
                dp.confirm()
            except ProcurementDomainError as exc:
                return ProcurementResult.fail(str(exc), "INVALID_STATE",
                                              operation_id=operation_id)

            receipt_id = None
            if dp.is_immediate_receipt():
                gr = _build_receipt(dp, actor_user_id, uow.sequences.next_number("REC", _year()))
                gr.complete()
                dp.mark_received()
                uow.receipts.save(gr)
                uow.direct_purchases.link_receipt(dp.id, gr.id)
                receipt_id = gr.id
            uow.direct_purchases.save(dp)

            uow.audit.record(action=ProcurementEvents.DIRECT_PURCHASE_CONFIRMED,
                             actor_user_id=actor_user_id, document_id=dp.id,
                             reason="confirmación", operation_id=operation_id,
                             branch_id=dp.branch_id, terminal_id=terminal_id)
            self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_CONFIRMED, document_id=dp.id,
                       operation_id=operation_id, actor_user_id=actor_user_id,
                       supplier_id=dp.supplier_id, branch_id=dp.branch_id,
                       total=str(dp.total().amount))
            if receipt_id is not None:
                self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_RECEIVED,
                           document_id=dp.id, operation_id=operation_id,
                           actor_user_id=actor_user_id, supplier_id=dp.supplier_id,
                           branch_id=dp.branch_id, goods_receipt_id=receipt_id,
                           warehouse_id=dp.warehouse_id,
                           source_channel=dp.source_channel.value,
                           document_number=dp.document_number,
                           supplier_ref=dp.supplier_id,
                           inventory_lines=[{"product_id": ln.product_id,
                                             "quantity": str(ln.inventory_quantity()),
                                             "unit_cost": str(ln.unit_cost.amount),
                                             "inventory_unit": ln.inventory_unit}
                                            for ln in dp.lines])
            else:
                self._emit(uow, ProcurementEvents.DIRECT_PURCHASE_RECEIPT_PENDING,
                           document_id=dp.id, operation_id=operation_id,
                           actor_user_id=actor_user_id, supplier_id=dp.supplier_id)
            # financial treatment
            if dp.payment_condition is PaymentCondition.IMMEDIATE_PAYMENT:
                self._emit(uow, ProcurementEvents.PURCHASE_PAYMENT_REQUESTED,
                           document_id=dp.id, operation_id=operation_id,
                           actor_user_id=actor_user_id, supplier_id=dp.supplier_id,
                           amount=str(dp.total().amount), payment_source=payment_source)
            else:
                self._emit(uow, ProcurementEvents.PURCHASE_PAYABLE_CREATED,
                           document_id=dp.id, operation_id=operation_id,
                           actor_user_id=actor_user_id, supplier_id=dp.supplier_id,
                           amount=str(dp.total().amount),
                           payment_condition=dp.payment_condition.value)
        return ProcurementResult.ok("Compra directa confirmada", entity_id=dp.id,
                                    operation_id=operation_id, status=dp.status.value,
                                    goods_receipt_id=receipt_id)


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


def _line_from_dict(raw: dict, currency_code: str) -> DirectPurchaseLine:
    unit_cost = Money(str(raw["unit_cost"]), raw.get("currency_code", currency_code))
    tax = Money(str(raw["tax"]), currency_code) if raw.get("tax") is not None else None
    discount = (Money(str(raw["discount"]), currency_code)
                if raw.get("discount") is not None else None)
    kwargs = {"purchase_unit": raw.get("purchase_unit", "PZA"),
              "inventory_unit": raw.get("inventory_unit", "PZA"),
              "conversion_factor": str(raw.get("conversion_factor", "1")),
              "destination_branch_id": raw.get("destination_branch_id"),
              "destination_warehouse_id": raw.get("destination_warehouse_id")}
    if tax is not None:
        kwargs["tax"] = tax
    if discount is not None:
        kwargs["discount"] = discount
    return DirectPurchaseLine.create(
        raw["product_id"], raw.get("description", ""), str(raw["quantity"]), unit_cost,
        **kwargs)


def _build_receipt(dp: DirectPurchase, actor_user_id: str, document_number) -> GoodsReceipt:
    gr = GoodsReceipt.create(document_number, dp.supplier_id, dp.branch_id, dp.warehouse_id,
                             received_by_user_id=actor_user_id, direct_purchase_id=dp.id)
    for ln in dp.lines:
        qty = ln.inventory_quantity()
        gr.add_line(GoodsReceiptLine.create(ln.product_id, qty, qty, qty))
    return gr
