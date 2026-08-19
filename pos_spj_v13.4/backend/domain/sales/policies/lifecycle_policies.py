"""Sale lifecycle invariants (master prompt §10, §13, §38). Mirrors
backend/domain/cash_register/policies/workflow_policies.py's
`CashShiftLifecyclePolicy` shape exactly — an enum-based transition table so
application services can validate rows from repositories without
reconstructing a full aggregate, while `Sale` itself reuses the same table.
"""

from __future__ import annotations

from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import (
    SaleCancellationNotAllowedError,
    SaleEmptyCartError,
    SaleInvalidStateError,
)


class SaleLifecyclePolicy:
    ACTIVE_STATUSES = frozenset({
        SaleStatus.DRAFT, SaleStatus.ACTIVE, SaleStatus.SUSPENDED,
        SaleStatus.CHECKOUT_PENDING, SaleStatus.PAYMENT_PENDING,
    })
    FINAL_STATUSES = frozenset({
        SaleStatus.CANCELLED, SaleStatus.REVERSED, SaleStatus.RETURNED_FULLY,
    })
    LINE_MUTABLE_STATUSES = frozenset({SaleStatus.DRAFT, SaleStatus.ACTIVE})

    TRANSITIONS = {
        (SaleStatus.DRAFT, SaleStatus.ACTIVE),
        (SaleStatus.ACTIVE, SaleStatus.SUSPENDED),
        (SaleStatus.SUSPENDED, SaleStatus.ACTIVE),
        (SaleStatus.ACTIVE, SaleStatus.CHECKOUT_PENDING),
        (SaleStatus.CHECKOUT_PENDING, SaleStatus.PAYMENT_PENDING),
        (SaleStatus.CHECKOUT_PENDING, SaleStatus.COMPLETED),
        (SaleStatus.PAYMENT_PENDING, SaleStatus.COMPLETED),
        (SaleStatus.PAYMENT_PENDING, SaleStatus.CHECKOUT_PENDING),
        (SaleStatus.DRAFT, SaleStatus.CANCELLED),
        (SaleStatus.ACTIVE, SaleStatus.CANCELLED),
        (SaleStatus.SUSPENDED, SaleStatus.CANCELLED),
        (SaleStatus.CHECKOUT_PENDING, SaleStatus.CANCELLED),
        (SaleStatus.COMPLETED, SaleStatus.RETURNED_PARTIALLY),
        (SaleStatus.COMPLETED, SaleStatus.RETURNED_FULLY),
        (SaleStatus.RETURNED_PARTIALLY, SaleStatus.RETURNED_FULLY),
        (SaleStatus.COMPLETED, SaleStatus.REVERSED),
    }

    @classmethod
    def normalize(cls, status: SaleStatus | str) -> SaleStatus:
        if isinstance(status, SaleStatus):
            return status
        try:
            return SaleStatus(str(status))
        except ValueError as exc:
            raise SaleInvalidStateError(f"Unknown sale status: {status}") from exc

    @classmethod
    def is_line_mutable(cls, status: SaleStatus | str) -> bool:
        return cls.normalize(status) in cls.LINE_MUTABLE_STATUSES

    @classmethod
    def ensure_transition(cls, *, current: SaleStatus | str, target: SaleStatus | str) -> None:
        current_status, target_status = cls.normalize(current), cls.normalize(target)
        if current_status in cls.FINAL_STATUSES:
            raise SaleInvalidStateError("Final sales cannot transition")
        if (current_status, target_status) not in cls.TRANSITIONS:
            raise SaleInvalidStateError(
                f"Invalid sale transition: {current_status.value} -> {target_status.value}")


class CheckoutPolicy:
    """Master prompt §13/§38: a sale cannot begin checkout without at least
    one line and a positive total — an empty or zero-value cart never reaches
    payment."""

    @staticmethod
    def ensure_can_checkout(*, status: SaleStatus, line_count: int, total) -> None:
        SaleLifecyclePolicy.ensure_transition(current=status, target=SaleStatus.CHECKOUT_PENDING)
        if line_count <= 0:
            raise SaleEmptyCartError("No se puede iniciar el cobro de un carrito vacío")
        if total <= 0:
            raise SaleEmptyCartError("El total de la venta debe ser mayor a cero")


class SaleCancellationPolicy:
    """Master prompt §42: cancellation only applies before payment is
    confirmed. A COMPLETED sale must be reversed (§44), never cancelled."""

    @staticmethod
    def ensure_can_cancel(*, status: SaleStatus, reason: str) -> None:
        if not (reason or "").strip():
            raise SaleCancellationNotAllowedError("La cancelación requiere un motivo")
        try:
            SaleLifecyclePolicy.ensure_transition(current=status, target=SaleStatus.CANCELLED)
        except SaleInvalidStateError as exc:
            raise SaleCancellationNotAllowedError(str(exc)) from exc
