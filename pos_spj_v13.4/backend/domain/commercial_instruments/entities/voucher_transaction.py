"""VoucherTransaction — one append-only voucher balance ledger entry (master
prompt §22). Mirrors ``backend/domain/loyalty/entities/loyalty_transaction.py``'s
design exactly, scoped to ``voucher_instance_id`` instead of an account:
``amount`` is the fixed, signed effect on balance ("no modificar movimientos
originales" — every correction is a new opposite-signed row); balance is
simply the sum of every non-``PENDING`` transaction's amount
(``VoucherBalancePolicy``, mirrors ``LoyaltyBalancePolicy``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.commercial_instruments.enums import (
    VoucherTransactionStatus,
    VoucherTransactionType,
)
from backend.domain.commercial_instruments.exceptions import (
    InvalidVoucherTransactionAmountError,
    InvalidVoucherTransactionStateError,
)
from backend.shared.ids import new_uuid

_CREDIT_TYPES = frozenset({
    VoucherTransactionType.ISSUE, VoucherTransactionType.RELEASE,
    VoucherTransactionType.RELOAD, VoucherTransactionType.REFUND,
})
_DEBIT_TYPES = frozenset({
    VoucherTransactionType.REDEEM, VoucherTransactionType.RESERVE,
    VoucherTransactionType.EXPIRE,
})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_amount(transaction_type: VoucherTransactionType, amount: Decimal) -> None:
    if not isinstance(amount, Decimal):
        raise InvalidVoucherTransactionAmountError("amount debe ser Decimal, nunca float")
    if amount == 0:
        raise InvalidVoucherTransactionAmountError("amount no puede ser cero")
    if transaction_type in _CREDIT_TYPES and amount < 0:
        raise InvalidVoucherTransactionAmountError(
            f"{transaction_type.value} requiere un monto positivo")
    if transaction_type in _DEBIT_TYPES and amount > 0:
        raise InvalidVoucherTransactionAmountError(
            f"{transaction_type.value} requiere un monto negativo")


@dataclass(slots=True)
class VoucherTransaction:
    id: str
    voucher_instance_id: str
    transaction_type: VoucherTransactionType
    amount: Decimal
    operation_id: str
    status: VoucherTransactionStatus = VoucherTransactionStatus.AVAILABLE
    sale_id: str | None = None
    reversal_transaction_id: str | None = None
    reason_code: str | None = None
    notes: str = ""
    created_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.voucher_instance_id:
            raise InvalidVoucherTransactionAmountError("voucher_instance_id es obligatorio")
        if not self.operation_id:
            raise InvalidVoucherTransactionAmountError("operation_id es obligatorio")
        _validate_amount(self.transaction_type, self.amount)

    @classmethod
    def _new(cls, transaction_type: VoucherTransactionType, *, voucher_instance_id: str,
              amount: Decimal, operation_id: str, status: VoucherTransactionStatus = VoucherTransactionStatus.AVAILABLE,
              sale_id: str | None = None, reason_code: str | None = None, notes: str = "",
              created_by_user_id: str | None = None) -> "VoucherTransaction":
        return cls(id=new_uuid(), voucher_instance_id=voucher_instance_id,
                   transaction_type=transaction_type, amount=amount, operation_id=operation_id,
                   status=status, sale_id=sale_id, reason_code=reason_code, notes=notes,
                   created_by_user_id=created_by_user_id)

    @classmethod
    def issue(cls, *, voucher_instance_id: str, amount: Decimal, operation_id: str,
              **kwargs) -> "VoucherTransaction":
        return cls._new(VoucherTransactionType.ISSUE, voucher_instance_id=voucher_instance_id,
                        amount=amount, operation_id=operation_id, **kwargs)

    @classmethod
    def redeem(cls, *, voucher_instance_id: str, amount: Decimal, operation_id: str,
               **kwargs) -> "VoucherTransaction":
        return cls._new(VoucherTransactionType.REDEEM, voucher_instance_id=voucher_instance_id,
                        amount=amount, operation_id=operation_id, **kwargs)

    @classmethod
    def reserve(cls, *, voucher_instance_id: str, amount: Decimal, operation_id: str,
                **kwargs) -> "VoucherTransaction":
        kwargs.pop("status", None)
        return cls._new(VoucherTransactionType.RESERVE, voucher_instance_id=voucher_instance_id,
                        amount=amount, operation_id=operation_id,
                        status=VoucherTransactionStatus.RESERVED, **kwargs)

    @classmethod
    def reload(cls, *, voucher_instance_id: str, amount: Decimal, operation_id: str,
               **kwargs) -> "VoucherTransaction":
        return cls._new(VoucherTransactionType.RELOAD, voucher_instance_id=voucher_instance_id,
                        amount=amount, operation_id=operation_id, **kwargs)

    @classmethod
    def adjustment(cls, *, voucher_instance_id: str, amount: Decimal, operation_id: str,
                   reason_code: str, **kwargs) -> "VoucherTransaction":
        if not (reason_code or "").strip():
            raise InvalidVoucherTransactionAmountError("El ajuste requiere reason_code")
        return cls._new(VoucherTransactionType.ADJUSTMENT,
                        voucher_instance_id=voucher_instance_id, amount=amount,
                        operation_id=operation_id, reason_code=reason_code, **kwargs)

    @classmethod
    def release_of(cls, reservation: "VoucherTransaction", *, operation_id: str,
                   created_by_user_id: str | None = None) -> "VoucherTransaction":
        if reservation.transaction_type is not VoucherTransactionType.RESERVE:
            raise InvalidVoucherTransactionStateError(
                "release_of solo aplica a una transacción RESERVE")
        return cls._new(VoucherTransactionType.RELEASE,
                        voucher_instance_id=reservation.voucher_instance_id,
                        amount=-reservation.amount, operation_id=operation_id,
                        reason_code=reservation.reason_code,
                        created_by_user_id=created_by_user_id)

    @classmethod
    def refund_of_original(cls, original_amount: Decimal, *, voucher_instance_id: str,
                           operation_id: str, reason_code: str,
                           created_by_user_id: str | None = None) -> "VoucherTransaction":
        return cls._new(VoucherTransactionType.REFUND, voucher_instance_id=voucher_instance_id,
                        amount=original_amount, operation_id=operation_id,
                        reason_code=reason_code, created_by_user_id=created_by_user_id)

    @classmethod
    def expire_of(cls, original: "VoucherTransaction", *, amount: Decimal,
                  operation_id: str, created_by_user_id: str | None = None) -> "VoucherTransaction":
        return cls._new(VoucherTransactionType.EXPIRE,
                        voucher_instance_id=original.voucher_instance_id, amount=amount,
                        operation_id=operation_id, created_by_user_id=created_by_user_id)

    @classmethod
    def reversal_of(cls, original: "VoucherTransaction", *, operation_id: str,
                    reason_code: str, created_by_user_id: str | None = None) -> "VoucherTransaction":
        if original.status is VoucherTransactionStatus.REVERSED:
            raise InvalidVoucherTransactionStateError("La transacción ya fue reversada")
        if not (reason_code or "").strip():
            raise InvalidVoucherTransactionAmountError("El reverso requiere reason_code")
        return cls._new(VoucherTransactionType.REVERSAL,
                        voucher_instance_id=original.voucher_instance_id,
                        amount=-original.amount, operation_id=operation_id,
                        reason_code=reason_code, created_by_user_id=created_by_user_id)

    def mark_consumed(self) -> None:
        if self.status is not VoucherTransactionStatus.RESERVED:
            raise InvalidVoucherTransactionStateError(
                f"Solo una reserva RESERVED puede consumirse (actual: {self.status.value})")
        self.status = VoucherTransactionStatus.CONSUMED

    def cancel_reservation(self) -> None:
        if self.status is not VoucherTransactionStatus.RESERVED:
            raise InvalidVoucherTransactionStateError(
                f"Solo una reserva RESERVED puede liberarse (actual: {self.status.value})")
        self.status = VoucherTransactionStatus.CANCELLED

    def mark_reversed(self, reversal_transaction_id: str) -> None:
        if self.status in (VoucherTransactionStatus.PENDING, VoucherTransactionStatus.CANCELLED,
                          VoucherTransactionStatus.REVERSED):
            raise InvalidVoucherTransactionStateError(
                f"No se puede reversar desde {self.status.value}")
        self.status = VoucherTransactionStatus.REVERSED
        self.reversal_transaction_id = reversal_transaction_id

    def counts_toward_balance(self) -> bool:
        return self.status is not VoucherTransactionStatus.PENDING
