"""Reconciliation policy — matching rules between statements and ledger lines (§15)."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.finance.entities.bank_statement import BankStatement, BankStatementLine
from backend.domain.finance.exceptions import ReconciliationError, ReconciliationMismatchError
from backend.domain.finance.value_objects.money import Money


class ReconciliationPolicy:
    def __init__(self, amount_tolerance: Decimal = Decimal("0")) -> None:
        self._tolerance = Decimal(amount_tolerance)

    def enforce_statement_consistency(self, statement: BankStatement) -> None:
        if not statement.is_internally_consistent():
            raise ReconciliationError(
                f"El estado no cuadra: saldo inicial {statement.opening_balance.to_string()} + "
                f"movimientos {statement.movement_total().to_string()} ≠ saldo final "
                f"{statement.closing_balance.to_string()}")

    def match_is_exact(self, statement_line: BankStatementLine, ledger_amount: Money) -> bool:
        """``True`` si cuadra al centavo; ``False`` si difiere dentro de la
        tolerancia (queda ADJUSTMENT_REQUIRED). Fuera de tolerancia se rechaza."""
        if statement_line.amount.currency_code != ledger_amount.currency_code:
            raise ReconciliationMismatchError("No se concilian importes de monedas distintas")
        difference = abs(statement_line.amount.amount - ledger_amount.amount)
        if difference == 0:
            return True
        if (statement_line.amount.amount > 0) != (ledger_amount.amount > 0):
            raise ReconciliationMismatchError(
                "La partida del estado y el movimiento del mayor van en sentido contrario")
        if difference > self._tolerance:
            raise ReconciliationMismatchError(
                f"Importes distintos: estado {statement_line.amount.to_string()} y mayor "
                f"{ledger_amount.to_string()} (tolerancia {self._tolerance}); registre un "
                "ajuste en lugar de forzar la conciliación")
        return False
