"""LoyaltyBalancePolicy — reconstructs an account's points balance from the
ledger (master prompt §11: "El saldo debe derivarse del ledger... debe
reconstruirse completamente desde el ledger"; §26 reservas).

Pure function over a list of ``LoyaltyTransaction``; no I/O. A cached/
materialized balance projection MAY exist in a later phase's persistence
layer, but it must always be re-derivable by replaying this same
calculation over the full ledger — never an independent source of truth.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.enums import TransactionStatus, TransactionType


class LoyaltyBalancePolicy:
    @staticmethod
    def balance(transactions: Iterable[LoyaltyTransaction]) -> Decimal:
        """Net points position: the sum of every transaction's signed
        ``points_amount`` except those still ``PENDING``. Already nets out
        active reservations (a RESERVE's negative amount counts the moment
        it is placed) — see the module-level docstring on
        ``LoyaltyTransaction`` for why status transitions never re-open this
        sum."""
        return sum(
            (t.points_amount for t in transactions if t.counts_toward_balance()),
            Decimal("0"),
        )

    @staticmethod
    def reserved_amount(transactions: Iterable[LoyaltyTransaction]) -> Decimal:
        """Points currently held by an active (not yet confirmed/released)
        reservation — informational split for UI ("disponible" vs
        "reservado"), already included in ``balance()``."""
        return sum(
            (-t.points_amount for t in transactions
             if t.transaction_type is TransactionType.RESERVE
             and t.status is TransactionStatus.RESERVED),
            Decimal("0"),
        )

    @staticmethod
    def lifetime_earned(transactions: Iterable[LoyaltyTransaction]) -> Decimal:
        """Total points ever earned (EARN + BONUS), ignoring redemptions/
        expirations — a common loyalty-tier evaluation input (§14)."""
        return sum(
            (t.points_amount for t in transactions
             if t.transaction_type in (TransactionType.EARN, TransactionType.BONUS)
             and t.counts_toward_balance()),
            Decimal("0"),
        )

    @staticmethod
    def fifo_remaining(credit: LoyaltyTransaction,
                       transactions: Iterable[LoyaltyTransaction]) -> Decimal:
        """Lo que AÚN queda de una acumulación, consumiendo primero lo más viejo
        (FIFO) — lo que caduca cuando vence (2026-10-02).

        Con FIFO, lo más nuevo se gasta al último: si de `credit` queda algo,
        todo lo acumulado después sigue intacto, así que
        ``queda = saldo - acumulado posterior``, acotado entre 0 y el monto
        original. Antes el barrido caducaba el monto ORIGINAL aunque ya se
        hubiera canjeado parte, y le quitaba al cliente puntos ganados después.
        Las liberaciones de apartados no cuentan como acumulación nueva.
        """
        transactions = list(transactions)
        saldo = LoyaltyBalancePolicy.balance(transactions)
        posterior = sum(
            (t.points_amount for t in transactions
             if t.id != credit.id and t.points_amount > 0
             and t.transaction_type in (TransactionType.EARN, TransactionType.BONUS,
                                        TransactionType.TRANSFER_IN, TransactionType.ADJUSTMENT)
             and t.status not in (TransactionStatus.PENDING, TransactionStatus.REVERSED,
                                  TransactionStatus.CANCELLED, TransactionStatus.EXPIRED)
             and (t.created_at, t.id) > (credit.created_at, credit.id)),
            Decimal("0"))
        return max(min(saldo - posterior, credit.points_amount), Decimal("0"))

