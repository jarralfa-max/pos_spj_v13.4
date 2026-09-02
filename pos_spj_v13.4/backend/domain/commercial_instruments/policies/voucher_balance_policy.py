"""VoucherBalancePolicy — reconstructs a voucher instance's balance from its
ledger (master prompt §22: "El saldo debe reconstruirse desde el ledger").
Mirrors ``backend/domain/loyalty/policies/balance_policy.py::LoyaltyBalancePolicy``
exactly."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from backend.domain.commercial_instruments.entities.voucher_transaction import (
    VoucherTransaction,
)
from backend.domain.commercial_instruments.enums import (
    VoucherTransactionStatus,
    VoucherTransactionType,
)


class VoucherBalancePolicy:
    @staticmethod
    def balance(transactions: Iterable[VoucherTransaction]) -> Decimal:
        return sum(
            (t.amount for t in transactions if t.counts_toward_balance()), Decimal("0"))

    @staticmethod
    def reserved_amount(transactions: Iterable[VoucherTransaction]) -> Decimal:
        return sum(
            (-t.amount for t in transactions
             if t.transaction_type is VoucherTransactionType.RESERVE
             and t.status is VoucherTransactionStatus.RESERVED),
            Decimal("0"))
