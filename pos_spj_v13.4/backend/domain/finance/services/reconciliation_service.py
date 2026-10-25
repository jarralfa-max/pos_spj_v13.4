"""ReconciliationService — domain matching between statements and ledger lines (§15).

Sugerencias por importe, fecha, referencia/folio, dentro de la tolerancia
configurada. Una partida y un movimiento del mayor se concilian a lo más una
vez; deshacer libera ambos y deja el historial.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.domain.finance.entities.bank_statement import BankStatement, BankStatementLine
from backend.domain.finance.entities.reconciliation import Reconciliation
from backend.domain.finance.exceptions import TransactionAlreadyReconciledError
from backend.domain.finance.policies.reconciliation_policy import ReconciliationPolicy
from backend.domain.finance.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class LedgerMovement:
    """Read-model of one postable ledger line eligible for matching."""

    journal_line_id: str
    amount: Money            # signed: positive inflow / negative outflow
    reference: str = ""
    movement_date: date | None = None


def _tokens(text: str) -> set[str]:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in (text or "").upper())
    return {token for token in cleaned.split() if len(token) >= 4}


class ReconciliationDomainService:
    def __init__(self, *, amount_tolerance: Decimal = Decimal("0"),
                 date_window_days: int = 0) -> None:
        self._policy = ReconciliationPolicy(amount_tolerance)
        self._tolerance = Decimal(amount_tolerance)
        self._window = int(date_window_days)

    def start(self, statement: BankStatement, operation_id: str) -> Reconciliation:
        self._policy.enforce_statement_consistency(statement)
        return Reconciliation.create(statement.treasury_account_id, statement.id, operation_id)

    def match(self, reconciliation: Reconciliation, statement_line: BankStatementLine,
              movement: LedgerMovement, matched_by: str) -> bool:
        """Concilia; devuelve ``True`` si fue exacto (``False`` = requiere ajuste)."""
        if not statement_line.is_open:
            raise TransactionAlreadyReconciledError(
                "La partida del estado ya está conciliada o ignorada")
        exact = self._policy.match_is_exact(statement_line, movement.amount)
        reconciliation.add_match(statement_line.id, movement.journal_line_id, matched_by)
        statement_line.mark_matched(movement.journal_line_id, exact=exact)
        return exact

    def complete(self, reconciliation: Reconciliation, statement: BankStatement,
                 completed_by: str, *, difference_reason: str | None = None) -> None:
        unmatched = sum(1 for line in statement.lines if not line.reconciled)
        reconciliation.complete(completed_by, unmatched_lines=unmatched,
                                difference_reason=difference_reason)

    def revert(self, reconciliation: Reconciliation, statement: BankStatement,
               reverted_by: str, reason: str) -> list[BankStatementLine]:
        """Revierte y devuelve las partidas del estado que quedan libres."""
        released_ids = {m.bank_statement_line_id for m in reconciliation.active_matches()}
        reconciliation.revert(reverted_by, reason)
        released = []
        for line in statement.lines:
            if line.id in released_ids or line.status.value == "IGNORED":
                line.release()
                released.append(line)
        return released

    # ── sugerencias ──────────────────────────────────────────────────────
    def score(self, line: BankStatementLine, movement: LedgerMovement) -> int | None:
        """0-100, o ``None`` si no es candidato (moneda, sentido, importe o fecha)."""
        if movement.amount.currency_code != line.amount.currency_code:
            return None
        if (movement.amount.amount > 0) != (line.amount.amount > 0):
            return None
        difference = abs(movement.amount.amount - line.amount.amount)
        if difference > self._tolerance:
            return None
        score = 60 if difference == 0 else 40
        if movement.movement_date is not None:
            days = abs((line.transaction_date - movement.movement_date).days)
            if days > self._window:
                return None
            score += 20 if days == 0 else 10
        reference = (line.external_reference or "").upper()
        if reference and reference in (movement.reference or "").upper():
            score += 20
        elif _tokens(line.description) & _tokens(movement.reference):
            score += 10
        return min(score, 100)

    def suggest_matches(self, statement: BankStatement, movements: list[LedgerMovement]
                        ) -> list[tuple[BankStatementLine, LedgerMovement, int]]:
        """Mejor candidato por partida; cada movimiento se usa a lo más una vez."""
        candidates: list[tuple[int, BankStatementLine, LedgerMovement]] = []
        for line in statement.lines:
            if not line.is_open:
                continue
            for movement in movements:
                value = self.score(line, movement)
                if value is not None:
                    candidates.append((value, line, movement))
        candidates.sort(key=lambda item: (-item[0], item[1].line_index))
        used_lines: set[str] = set()
        used_movements: set[str] = set()
        result: list[tuple[BankStatementLine, LedgerMovement, int]] = []
        for value, line, movement in candidates:
            if line.id in used_lines or movement.journal_line_id in used_movements:
                continue
            used_lines.add(line.id)
            used_movements.add(movement.journal_line_id)
            result.append((line, movement, value))
        return result
