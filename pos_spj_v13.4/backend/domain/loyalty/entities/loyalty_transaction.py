"""LoyaltyTransaction — one append-only points ledger entry (§11).

Design decision (documented, not fabricated — the master prompt gives the
vocabulary in §11 but not an executable balance algorithm):

``points_amount`` is always the SIGNED effect on the account's balance
(positive = credit, negative = debit), fixed at creation time and never
edited afterwards ("No modificar movimientos originales" — §11). Every
correction (release a reservation, expire points, reverse a transaction) is
always a brand-new transaction carrying the opposite-signed amount — never a
retroactive edit of the original row's amount. This means the ledger balance
is simply the sum of every non-``PENDING`` transaction's ``points_amount``
(see ``backend/domain/loyalty/policies/balance_policy.py``); a transaction's
``status`` afterwards (``RESERVED``→``CONSUMED``/``CANCELLED``,
``AVAILABLE``→``EXPIRED``/``REVERSED``) is bookkeeping metadata for business
rules ("can this reservation still be released?") and reporting, not a
second, competing source of truth for the balance.

``PENDING`` is the only status excluded from the balance sum — a transaction
whose ``available_at`` is still in the future (e.g. points that unlock a few
days after purchase) has not happened yet as far as the account is
concerned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty.enums import TransactionStatus, TransactionType
from backend.domain.loyalty.exceptions import (
    InvalidLoyaltyTransactionAmountError,
    InvalidLoyaltyTransactionStateError,
)
from backend.shared.ids import new_uuid

_CREDIT_TYPES = frozenset({
    TransactionType.EARN, TransactionType.BONUS, TransactionType.RELEASE,
    TransactionType.TRANSFER_IN,
})
_DEBIT_TYPES = frozenset({
    TransactionType.REDEEM, TransactionType.RESERVE, TransactionType.EXPIRE,
    TransactionType.TRANSFER_OUT,
})
_EITHER_SIGN_TYPES = frozenset({TransactionType.ADJUSTMENT, TransactionType.REVERSAL})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_amount(transaction_type: TransactionType, points_amount: Decimal) -> None:
    if not isinstance(points_amount, Decimal):
        raise InvalidLoyaltyTransactionAmountError(
            "points_amount debe ser Decimal, nunca float")
    if points_amount == 0:
        raise InvalidLoyaltyTransactionAmountError("points_amount no puede ser cero")
    if transaction_type in _CREDIT_TYPES and points_amount < 0:
        raise InvalidLoyaltyTransactionAmountError(
            f"{transaction_type.value} requiere un monto positivo")
    if transaction_type in _DEBIT_TYPES and points_amount > 0:
        raise InvalidLoyaltyTransactionAmountError(
            f"{transaction_type.value} requiere un monto negativo")


@dataclass(slots=True)
class LoyaltyTransaction:
    id: str
    loyalty_account_id: str
    transaction_type: TransactionType
    points_amount: Decimal
    operation_id: str
    membership_id: str | None = None
    status: TransactionStatus = TransactionStatus.AVAILABLE
    source_module: str = ""
    source_document_type: str | None = None
    source_document_id: str | None = None
    sale_id: str | None = None
    branch_id: str | None = None
    reversal_transaction_id: str | None = None
    reason_code: str | None = None
    notes: str = ""
    created_by_user_id: str | None = None
    available_at: str | None = None
    expires_at: str | None = None
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.loyalty_account_id:
            raise InvalidLoyaltyTransactionAmountError("loyalty_account_id es obligatorio")
        if not self.operation_id:
            raise InvalidLoyaltyTransactionAmountError("operation_id es obligatorio")
        _validate_amount(self.transaction_type, self.points_amount)

    # ── factories ──────────────────────────────────────────────────────────
    @classmethod
    def _new(cls, transaction_type: TransactionType, *, loyalty_account_id: str,
              points_amount: Decimal, operation_id: str, membership_id: str | None = None,
              status: TransactionStatus = TransactionStatus.AVAILABLE,
              source_module: str = "", source_document_type: str | None = None,
              source_document_id: str | None = None, sale_id: str | None = None,
              branch_id: str | None = None, reason_code: str | None = None,
              notes: str = "", created_by_user_id: str | None = None,
              available_at: str | None = None, expires_at: str | None = None,
              ) -> "LoyaltyTransaction":
        initial_status = TransactionStatus.PENDING if available_at else status
        return cls(
            id=new_uuid(), loyalty_account_id=loyalty_account_id,
            membership_id=membership_id, transaction_type=transaction_type,
            points_amount=points_amount, operation_id=operation_id,
            status=initial_status, source_module=source_module,
            source_document_type=source_document_type,
            source_document_id=source_document_id, sale_id=sale_id,
            branch_id=branch_id, reason_code=reason_code, notes=notes,
            created_by_user_id=created_by_user_id, available_at=available_at,
            expires_at=expires_at,
        )

    @classmethod
    def earn(cls, *, loyalty_account_id: str, points_amount: Decimal, operation_id: str,
              **kwargs) -> "LoyaltyTransaction":
        return cls._new(TransactionType.EARN, loyalty_account_id=loyalty_account_id,
                         points_amount=points_amount, operation_id=operation_id, **kwargs)

    @classmethod
    def bonus(cls, *, loyalty_account_id: str, points_amount: Decimal, operation_id: str,
               **kwargs) -> "LoyaltyTransaction":
        return cls._new(TransactionType.BONUS, loyalty_account_id=loyalty_account_id,
                         points_amount=points_amount, operation_id=operation_id, **kwargs)

    @classmethod
    def redeem(cls, *, loyalty_account_id: str, points_amount: Decimal, operation_id: str,
                **kwargs) -> "LoyaltyTransaction":
        return cls._new(TransactionType.REDEEM, loyalty_account_id=loyalty_account_id,
                         points_amount=points_amount, operation_id=operation_id, **kwargs)

    @classmethod
    def reserve(cls, *, loyalty_account_id: str, points_amount: Decimal, operation_id: str,
                 **kwargs) -> "LoyaltyTransaction":
        kwargs.pop("status", None)
        return cls._new(TransactionType.RESERVE, loyalty_account_id=loyalty_account_id,
                         points_amount=points_amount, operation_id=operation_id,
                         status=TransactionStatus.RESERVED, **kwargs)

    @classmethod
    def adjustment(cls, *, loyalty_account_id: str, points_amount: Decimal, operation_id: str,
                    reason_code: str, **kwargs) -> "LoyaltyTransaction":
        if not (reason_code or "").strip():
            raise InvalidLoyaltyTransactionAmountError("El ajuste requiere reason_code")
        return cls._new(TransactionType.ADJUSTMENT, loyalty_account_id=loyalty_account_id,
                         points_amount=points_amount, operation_id=operation_id,
                         reason_code=reason_code, **kwargs)

    @classmethod
    def transfer_in(cls, *, loyalty_account_id: str, points_amount: Decimal, operation_id: str,
                      **kwargs) -> "LoyaltyTransaction":
        return cls._new(TransactionType.TRANSFER_IN, loyalty_account_id=loyalty_account_id,
                         points_amount=points_amount, operation_id=operation_id, **kwargs)

    @classmethod
    def transfer_out(cls, *, loyalty_account_id: str, points_amount: Decimal, operation_id: str,
                       **kwargs) -> "LoyaltyTransaction":
        return cls._new(TransactionType.TRANSFER_OUT, loyalty_account_id=loyalty_account_id,
                         points_amount=points_amount, operation_id=operation_id, **kwargs)

    @classmethod
    def release_of(cls, reservation: "LoyaltyTransaction", *, operation_id: str,
                     created_by_user_id: str | None = None, notes: str = "") -> "LoyaltyTransaction":
        """The offsetting credit for a cancelled reservation. Caller must
        also call ``reservation.cancel_reservation()`` on the original."""
        if reservation.transaction_type is not TransactionType.RESERVE:
            raise InvalidLoyaltyTransactionStateError(
                "release_of solo aplica a una transacción RESERVE")
        return cls._new(
            TransactionType.RELEASE, loyalty_account_id=reservation.loyalty_account_id,
            membership_id=reservation.membership_id, points_amount=-reservation.points_amount,
            operation_id=operation_id, source_module=reservation.source_module,
            reason_code=reservation.reason_code, notes=notes,
            created_by_user_id=created_by_user_id,
        )

    @classmethod
    def expire_of(cls, original: "LoyaltyTransaction", *, points_amount: Decimal,
                    operation_id: str, created_by_user_id: str | None = None) -> "LoyaltyTransaction":
        """The offsetting debit for points that expired. ``points_amount``
        is a separate, explicit (negative) argument rather than always
        mirroring the full original amount, since a partial expiration
        (some of an EARN entry already redeemed) is a real case."""
        return cls._new(
            TransactionType.EXPIRE, loyalty_account_id=original.loyalty_account_id,
            membership_id=original.membership_id, points_amount=points_amount,
            operation_id=operation_id, source_module=original.source_module,
            created_by_user_id=created_by_user_id,
        )

    @classmethod
    def reversal_of(cls, original: "LoyaltyTransaction", *, operation_id: str,
                      reason_code: str, created_by_user_id: str | None = None,
                      notes: str = "") -> "LoyaltyTransaction":
        if original.status is TransactionStatus.REVERSED:
            raise InvalidLoyaltyTransactionStateError("La transacción ya fue reversada")
        if not (reason_code or "").strip():
            raise InvalidLoyaltyTransactionAmountError("El reverso requiere reason_code")
        return cls._new(
            TransactionType.REVERSAL, loyalty_account_id=original.loyalty_account_id,
            membership_id=original.membership_id, points_amount=-original.points_amount,
            operation_id=operation_id, source_module=original.source_module,
            reason_code=reason_code, notes=notes, created_by_user_id=created_by_user_id,
        )

    # ── status transitions (bookkeeping, not balance-affecting — see module docstring) ──
    def mark_available(self) -> None:
        if self.status is not TransactionStatus.PENDING:
            raise InvalidLoyaltyTransactionStateError(
                f"Solo una transacción PENDING pasa a AVAILABLE (actual: {self.status.value})")
        self.status = TransactionStatus.AVAILABLE

    def mark_consumed(self) -> None:
        if self.status is not TransactionStatus.RESERVED:
            raise InvalidLoyaltyTransactionStateError(
                f"Solo una reserva RESERVED puede consumirse (actual: {self.status.value})")
        self.status = TransactionStatus.CONSUMED

    def cancel_reservation(self) -> None:
        if self.status is not TransactionStatus.RESERVED:
            raise InvalidLoyaltyTransactionStateError(
                f"Solo una reserva RESERVED puede liberarse (actual: {self.status.value})")
        self.status = TransactionStatus.CANCELLED

    def mark_expired(self) -> None:
        if self.status is not TransactionStatus.AVAILABLE:
            raise InvalidLoyaltyTransactionStateError(
                f"Solo una transacción AVAILABLE puede expirar (actual: {self.status.value})")
        self.status = TransactionStatus.EXPIRED

    def mark_reversed(self, reversal_transaction_id: str) -> None:
        if self.status in (TransactionStatus.PENDING, TransactionStatus.CANCELLED,
                           TransactionStatus.REVERSED):
            raise InvalidLoyaltyTransactionStateError(
                f"No se puede reversar desde {self.status.value}")
        if not reversal_transaction_id:
            raise InvalidLoyaltyTransactionStateError(
                "mark_reversed requiere el id de la transacción de reverso")
        self.status = TransactionStatus.REVERSED
        self.reversal_transaction_id = reversal_transaction_id

    def counts_toward_balance(self) -> bool:
        return self.status is not TransactionStatus.PENDING
