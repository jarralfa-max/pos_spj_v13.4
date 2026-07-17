"""Procurement domain policies (PUR-2 security core + PUR-3 workflow selection).

Pure rules, no I/O. Authorization/limits/segregation live here so every use case
re-validates them (hiding a button is never security). The UI never decides the
flow via scattered conditionals — PurchaseWorkflowPolicy does.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from enum import Enum

from backend.domain.procurement.enums import PaymentSource, PurchaseFlow
from backend.domain.procurement.exceptions import (
    AuthorizationRequiredError,
    InvalidPaymentSourceError,
    PurchaseLimitExceededError,
    SegregationOfDutiesError,
    SupplierNotEligibleError,
    TimeWindowError,
)
from backend.domain.procurement.value_objects import (
    Money,
    PurchaseLimit,
    ReceivingWindow,
)


class LimitEvaluation(str, Enum):
    WITHIN = "WITHIN"                    # can execute directly
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"  # over approval threshold, under hard cap
    EXCEEDS = "EXCEEDS"                  # over the hard per-transaction cap


class UserPurchaseLimitPolicy:
    """Evaluates an amount against a configurable limit (never hardcoded)."""

    def evaluate(self, amount: Money, limit: PurchaseLimit | None) -> LimitEvaluation:
        if limit is None:
            return LimitEvaluation.WITHIN
        value = amount.amount
        cap = limit.maximum_per_transaction
        threshold = limit.requires_approval_above
        if cap is not None and value > cap:
            return LimitEvaluation.EXCEEDS
        if threshold is not None and value > threshold:
            return LimitEvaluation.REQUIRES_APPROVAL
        return LimitEvaluation.WITHIN

    def enforce_direct_execution(self, amount: Money, limit: PurchaseLimit | None) -> None:
        """Raise when a direct execution needs escalation/authorization."""
        result = self.evaluate(amount, limit)
        if result is LimitEvaluation.REQUIRES_APPROVAL:
            raise AuthorizationRequiredError(
                "El monto supera el umbral de autorización del usuario")
        if result is LimitEvaluation.EXCEEDS:
            raise PurchaseLimitExceededError(
                "El monto supera el límite máximo del usuario; requiere flujo de aprobación")


class SupplierEligibilityPolicy:
    """A supplier must be active and free of a purchasing block to be bought from."""

    def enforce(self, *, active: bool, purchasing_blocked: bool,
                general_blocked: bool = False) -> None:
        if not active:
            raise SupplierNotEligibleError("El proveedor no está activo")
        if purchasing_blocked or general_blocked:
            raise SupplierNotEligibleError("El proveedor tiene bloqueo de compras")


class DirectPurchasePolicy:
    """Gate for the fast direct-purchase flow (§12)."""

    def __init__(self) -> None:
        self._limits = UserPurchaseLimitPolicy()
        self._supplier = SupplierEligibilityPolicy()

    def enforce_can_execute(self, *, amount: Money, branch_allows_direct: bool,
                            supplier_active: bool, supplier_purchasing_blocked: bool,
                            user_limit: PurchaseLimit | None,
                            payment_allowed: bool = True) -> None:
        if not branch_allows_direct:
            raise SupplierNotEligibleError(
                "La sucursal no tiene habilitada la compra directa")
        self._supplier.enforce(active=supplier_active,
                               purchasing_blocked=supplier_purchasing_blocked)
        if not payment_allowed:
            raise InvalidPaymentSourceError("La condición de pago no está permitida")
        # limits last: raises AuthorizationRequired/LimitExceeded to escalate
        self._limits.enforce_direct_execution(amount, user_limit)


class PurchaseWorkflowPolicy:
    """Selects the flow. The UI must NOT decide this via scattered conditionals."""

    def __init__(self) -> None:
        self._limits = UserPurchaseLimitPolicy()

    def select_flow(self, *, amount: Money, is_emergency: bool = False,
                    requires_quotation: bool = False,
                    user_limit: PurchaseLimit | None = None,
                    branch_allows_direct: bool = True) -> PurchaseFlow:
        if is_emergency:
            return PurchaseFlow.EMERGENCY_FLOW
        if requires_quotation:
            return PurchaseFlow.ENTERPRISE_FLOW
        evaluation = self._limits.evaluate(amount, user_limit)
        if evaluation is LimitEvaluation.EXCEEDS:
            return PurchaseFlow.ENTERPRISE_FLOW
        if not branch_allows_direct:
            return PurchaseFlow.STANDARD_FLOW
        # WITHIN or REQUIRES_APPROVAL both stay in the direct flow (the latter with
        # a hot authorization step).
        return PurchaseFlow.DIRECT_FLOW


class ImmediatePaymentPolicy:
    """Immediate payment must go through an authorized financial source — NEVER the
    POS operative cash (§21)."""

    _FORBIDDEN = frozenset({"POS_CASH", "POS_OPERATIVE_CASH", "CAJA_POS"})

    def enforce_source(self, source: str, *, allowed_sources: set[str] | None = None) -> None:
        if source in self._FORBIDDEN:
            raise InvalidPaymentSourceError(
                "El pago no puede salir de la caja operativa del POS")
        valid = {s.value for s in PaymentSource}
        if source not in valid:
            raise InvalidPaymentSourceError(f"Fuente de pago no configurada: {source}")
        if allowed_sources is not None and source not in allowed_sources:
            raise InvalidPaymentSourceError(
                f"La fuente {source} no está permitida por policy")


class TimeWindowPolicy:
    def enforce_within_window(self, moment: time, window: ReceivingWindow | None) -> None:
        if window is None:
            return
        if not window.allows(moment):
            raise TimeWindowError(
                "La compra directa está fuera del horario permitido")


class SegregationOfDutiesPolicy:
    """Enforces separation of duties (§65). Conflicts raise SegregationOfDutiesError."""

    def enforce_distinct(self, user_a: str | None, user_b: str | None, rule: str) -> None:
        if user_a and user_b and user_a == user_b:
            raise SegregationOfDutiesError(f"Separación de funciones: {rule}")

    def enforce_requester_not_self_approving_above_limit(
            self, requester_id: str, approver_id: str, *, within_limit: bool) -> None:
        if not within_limit:
            self.enforce_distinct(
                requester_id, approver_id,
                "quien realiza una compra elevada no puede autorizarla")

    def enforce_receiver_not_price_changer(self, receiver_id: str,
                                           price_changer_id: str) -> None:
        self.enforce_distinct(receiver_id, price_changer_id,
                              "quien recibe no modifica precios")

    def enforce_invoice_clerk_not_variance_releaser(self, clerk_id: str,
                                                    releaser_id: str) -> None:
        self.enforce_distinct(clerk_id, releaser_id,
                              "quien captura la factura no libera diferencias sensibles")

    def enforce_payment_requester_not_executor(self, requester_id: str,
                                               executor_id: str) -> None:
        self.enforce_distinct(requester_id, executor_id,
                              "quien solicita el pago no lo ejecuta")
