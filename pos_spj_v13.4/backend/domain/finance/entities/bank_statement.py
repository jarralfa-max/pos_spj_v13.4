"""BankStatement entities — imported statements for reconciliation (§15).

Una partida pasa por UNMATCHED → SUGGESTED → MATCHED, o IGNORED (con motivo),
o ADJUSTMENT_REQUIRED (conciliada con una diferencia dentro de la tolerancia
que sólo un ajuste autorizado cierra). El estado tiene una huella de contenido:
importar dos veces el mismo estado se rechaza.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.finance.enums import StatementLineStatus
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    TransactionAlreadyReconciledError,
)
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Formatos de origen soportados; ``API`` queda preparado para integración bancaria.
STATEMENT_FORMATS = frozenset({"MANUAL", "CSV", "XLSX", "API"})


@dataclass(slots=True)
class BankStatementLine:
    id: str
    bank_statement_id: str
    transaction_date: date
    description: str
    amount: Money            # positive = inflow, negative = outflow
    external_reference: str = ""
    matched_journal_line_id: str | None = None
    line_index: int = 0
    status: StatementLineStatus = StatementLineStatus.UNMATCHED
    suggested_journal_line_id: str | None = None
    suggestion_score: int | None = None
    ignored_reason: str | None = None
    ignored_by: str | None = None
    adjustment_journal_entry_id: str | None = None

    @classmethod
    def create(cls, bank_statement_id: str, transaction_date: date, description: str,
               amount: Money, *, external_reference: str = "",
               line_index: int = 0) -> "BankStatementLine":
        if amount.is_zero():
            raise FinanceDomainError("Una partida del estado no puede ser de importe cero")
        return cls(
            id=new_uuid(), bank_statement_id=bank_statement_id,
            transaction_date=transaction_date, description=(description or "").strip(),
            amount=amount, external_reference=(external_reference or "").strip(),
            line_index=line_index,
        )

    @property
    def reconciled(self) -> bool:
        """Cuenta como resuelta para cerrar la conciliación."""
        return self.status in (StatementLineStatus.MATCHED, StatementLineStatus.IGNORED)

    @property
    def is_open(self) -> bool:
        return self.status in (StatementLineStatus.UNMATCHED, StatementLineStatus.SUGGESTED)

    def suggest(self, journal_line_id: str, score: int) -> None:
        if not self.is_open:
            return
        self.status = StatementLineStatus.SUGGESTED
        self.suggested_journal_line_id = journal_line_id
        self.suggestion_score = int(score)

    def mark_matched(self, journal_line_id: str, *, exact: bool) -> None:
        if not self.is_open:
            raise TransactionAlreadyReconciledError(
                f"La partida del estado ya está {self.status.value}; no se concilia dos veces")
        self.matched_journal_line_id = journal_line_id
        self.suggested_journal_line_id = None
        self.status = (StatementLineStatus.MATCHED if exact
                       else StatementLineStatus.ADJUSTMENT_REQUIRED)

    def settle_adjustment(self, journal_entry_id: str) -> None:
        if self.status is not StatementLineStatus.ADJUSTMENT_REQUIRED:
            raise FinanceDomainError("La partida no tiene una diferencia pendiente de ajuste")
        self.adjustment_journal_entry_id = journal_entry_id
        self.status = StatementLineStatus.MATCHED

    def ignore(self, reason: str, by: str) -> None:
        if not self.is_open:
            raise TransactionAlreadyReconciledError(
                f"La partida ya está {self.status.value}; no se ignora")
        if not (reason or "").strip():
            raise FinanceDomainError("Ignorar una partida exige el motivo")
        self.status = StatementLineStatus.IGNORED
        self.ignored_reason = reason.strip()
        self.ignored_by = by
        self.suggested_journal_line_id = None

    def release(self) -> None:
        """Deshacer: la partida vuelve a estar libre (el historial vive en el match)."""
        self.status = StatementLineStatus.UNMATCHED
        self.matched_journal_line_id = None
        self.suggested_journal_line_id = None
        self.suggestion_score = None
        self.ignored_reason = None
        self.ignored_by = None


@dataclass(slots=True)
class BankStatement:
    id: str
    treasury_account_id: str
    statement_date: date
    opening_balance: Money
    closing_balance: Money
    operation_id: str
    imported_at: str = field(default_factory=_utcnow)
    lines: list[BankStatementLine] = field(default_factory=list)
    source_format: str = "MANUAL"
    file_name: str = ""
    content_hash: str = ""
    imported_by: str | None = None

    @classmethod
    def create(cls, treasury_account_id: str, statement_date: date,
               opening_balance: Money, closing_balance: Money, operation_id: str, *,
               source_format: str = "MANUAL", file_name: str = "",
               imported_by: str | None = None) -> "BankStatement":
        if not treasury_account_id:
            raise FinanceDomainError("El estado de cuenta requiere su cuenta de tesorería")
        source_format = (source_format or "MANUAL").upper()
        if source_format not in STATEMENT_FORMATS:
            raise FinanceDomainError(f"Formato de estado no soportado: {source_format}")
        return cls(
            id=new_uuid(), treasury_account_id=treasury_account_id,
            statement_date=statement_date, opening_balance=opening_balance,
            closing_balance=closing_balance, operation_id=operation_id,
            source_format=source_format, file_name=(file_name or "").strip(),
            imported_by=imported_by,
        )

    def add_line(self, transaction_date: date, description: str, amount: Money,
                 external_reference: str = "") -> BankStatementLine:
        line = BankStatementLine.create(
            self.id, transaction_date, description, amount,
            external_reference=external_reference, line_index=len(self.lines),
        )
        self.lines.append(line)
        return line

    def seal(self) -> str:
        """Huella del contenido (cuenta, saldos, partidas). Dos importaciones del
        mismo estado producen la misma huella aunque cambie el archivo."""
        parts = [self.treasury_account_id, self.statement_date.isoformat(),
                 self.opening_balance.to_string(), self.closing_balance.to_string()]
        for line in self.lines:
            parts.append("|".join((line.transaction_date.isoformat(), line.amount.to_string(),
                                   line.external_reference, line.description)))
        self.content_hash = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
        return self.content_hash

    def movement_total(self) -> Money:
        total = Money.zero(self.opening_balance.currency_code)
        for line in self.lines:
            total = total.add(line.amount)
        return total

    def is_internally_consistent(self) -> bool:
        return self.opening_balance.add(self.movement_total()).amount == self.closing_balance.amount

    def line(self, line_id: str) -> BankStatementLine:
        for line in self.lines:
            if line.id == line_id:
                return line
        raise FinanceDomainError("La partida no pertenece a este estado de cuenta")
