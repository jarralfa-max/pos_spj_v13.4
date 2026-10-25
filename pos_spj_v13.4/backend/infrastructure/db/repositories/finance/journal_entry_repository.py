"""JournalEntry repository — entries with lines, idempotency lookups, drafts.

Un asiento contabilizado nunca se reescribe: ``update_status`` sólo cambia su
estado (POSTED → REVERSED) y ``update_draft`` se niega a tocar algo que no sea
un borrador o validado (la guarda está también en el ``WHERE`` del SQL).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.finance.entities.journal_entry import JournalEntry, JournalLine
from backend.domain.finance.enums import JournalEntryStatus, LineRole, PostingPurpose
from backend.domain.finance.exceptions import JournalEntryImmutableError
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_ENTRY_FIELDS = (
    "id", "journal_id", "entry_number", "entry_date", "posting_date", "fiscal_period_id",
    "description", "currency_code", "base_currency_code", "status", "source_module",
    "source_document_type", "source_document_id", "posting_purpose", "operation_id",
    "branch_id", "reversal_of_entry_id", "reversed_by_entry_id", "created_by",
    "validated_by", "validated_at", "posted_by", "posted_at", "cancelled_by",
    "cancel_reason", "created_at", "updated_at",
)
#: El id se acuña en el dominio (UUIDv7) y va explícito en cada INSERT.
_ENTRY_COLUMNS = "id, " + ", ".join(_ENTRY_FIELDS[1:])
_LINE_FIELDS = (
    "id", "journal_entry_id", "account_id", "description", "debit_amount", "credit_amount",
    "currency_code", "exchange_rate", "base_debit_amount", "base_credit_amount", "line_role",
    "branch_id", "cost_center_id", "profit_center_id", "project_id", "department_id",
    "customer_id", "supplier_id", "employee_id", "product_id", "source_reference",
    "line_index",
)
_LINE_COLUMNS = "id, " + ", ".join(_LINE_FIELDS[1:])
_EDITABLE = (JournalEntryStatus.DRAFT, JournalEntryStatus.VALIDATED)


def _line_to_entity(row: dict, base_currency: str) -> JournalLine:
    currency = row["currency_code"]
    return JournalLine(
        id=row["id"],
        journal_entry_id=row["journal_entry_id"],
        account_id=row["account_id"],
        description=row["description"],
        debit=Money.from_string(row["debit_amount"], currency),
        credit=Money.from_string(row["credit_amount"], currency),
        exchange_rate=Decimal(str(row["exchange_rate"] or "1")),
        base_debit=Money.from_string(row["base_debit_amount"], base_currency),
        base_credit=Money.from_string(row["base_credit_amount"], base_currency),
        line_role=LineRole(row["line_role"]),
        cost_center_id=row["cost_center_id"],
        profit_center_id=row["profit_center_id"],
        branch_id=row["branch_id"],
        project_id=row["project_id"],
        department_id=row["department_id"],
        customer_id=row["customer_id"],
        supplier_id=row["supplier_id"],
        employee_id=row["employee_id"],
        product_id=row["product_id"],
        source_reference=row["source_reference"] or "",
        line_index=row["line_index"],
    )


def _line_params(line: JournalLine) -> tuple:
    return (line.id, line.journal_entry_id, line.account_id, line.description,
            line.debit.to_string(), line.credit.to_string(), line.debit.currency_code,
            format(line.exchange_rate, "f"), line.base_debit.to_string(),
            line.base_credit.to_string(), line.line_role.value, line.branch_id,
            line.cost_center_id, line.profit_center_id, line.project_id, line.department_id,
            line.customer_id, line.supplier_id, line.employee_id, line.product_id,
            line.source_reference or "", line.line_index)


def _entry_params(entry: JournalEntry) -> tuple:
    ref = entry.posting_reference
    return (entry.id, entry.journal_id, entry.entry_number, entry.entry_date.isoformat(),
            entry.posting_date.isoformat(), entry.fiscal_period_id, entry.description,
            entry.currency_code, entry.base_currency_code, entry.status.value,
            ref.source_module, entry.source_document_type, ref.source_document_id,
            ref.posting_purpose.value, ref.operation_id, entry.branch_id,
            entry.reversal_of_entry_id, entry.reversed_by_entry_id, entry.created_by,
            entry.validated_by, entry.validated_at, entry.posted_by, entry.posted_at,
            entry.cancelled_by, entry.cancel_reason, entry.created_at, entry.updated_at)


class JournalEntryRepository(FinanceRepositoryBase):
    def save(self, entry: JournalEntry) -> None:
        placeholders = ",".join("?" for _ in _ENTRY_FIELDS)
        self._execute(f"INSERT INTO journal_entries ({_ENTRY_COLUMNS}) VALUES ({placeholders})",
                      _entry_params(entry))
        self._insert_lines(entry)

    def _insert_lines(self, entry: JournalEntry) -> None:
        placeholders = ",".join("?" for _ in _LINE_FIELDS)
        for line in entry.lines:
            self._execute(f"INSERT INTO journal_lines ({_LINE_COLUMNS}) VALUES ({placeholders})",
                          _line_params(line))

    def update_draft(self, entry: JournalEntry) -> None:
        """Reescribe un borrador/validado completo (cabecera y líneas). Un
        asiento contabilizado jamás pasa por aquí."""
        current = self._query_one("SELECT status FROM journal_entries WHERE id=?", (entry.id,))
        if current is None or JournalEntryStatus(current["status"]) not in _EDITABLE:
            raise JournalEntryImmutableError(
                f"El asiento {entry.entry_number} ya no es un borrador; no se reescribe")
        assignments = ", ".join(f"{name}=?" for name in _ENTRY_FIELDS[1:])
        params = _entry_params(entry)[1:] + (entry.id,)
        self._execute(f"UPDATE journal_entries SET {assignments} WHERE id=?"
                      " AND status IN ('DRAFT','VALIDATED')", params)
        self._execute("DELETE FROM journal_lines WHERE journal_entry_id=?", (entry.id,))
        self._insert_lines(entry)

    def update_draft_to_posted(self, entry: JournalEntry) -> None:
        """Un borrador VALIDADO pasa a POSTED con su folio definitivo. Las
        líneas no cambian; la guarda del ``WHERE`` impide tocar otro estado."""
        cursor = self._update("journal_entries", {
            "entry_number": entry.entry_number, "fiscal_period_id": entry.fiscal_period_id,
            "status": entry.status.value, "posted_by": entry.posted_by,
            "posted_at": entry.posted_at, "updated_at": entry.updated_at,
        }, where="id=? AND status='VALIDATED'", params=(entry.id,))
        if cursor.rowcount == 0:
            raise JournalEntryImmutableError(
                f"El asiento {entry.entry_number} no estaba validado; no se contabiliza")

    def update_status(self, entry: JournalEntry) -> None:
        self._execute(
            "UPDATE journal_entries SET status=?, posted_at=?, posted_by=?, reversed_by_entry_id=?,"
            " updated_at=? WHERE id=?",
            (entry.status.value, entry.posted_at, entry.posted_by, entry.reversed_by_entry_id,
             entry.updated_at, entry.id),
        )

    def get(self, entry_id: str) -> JournalEntry | None:
        row = self._query_one(
            f"SELECT {_ENTRY_COLUMNS} FROM journal_entries WHERE id=?", (entry_id,))
        return self._hydrate(row) if row else None

    def find_by_posting_reference(
        self, source_module: str, source_document_id: str, posting_purpose: PostingPurpose,
    ) -> JournalEntry | None:
        row = self._query_one(
            f"SELECT {_ENTRY_COLUMNS} FROM journal_entries"
            " WHERE source_module=? AND source_document_id=? AND posting_purpose=?",
            (source_module, source_document_id, posting_purpose.value),
        )
        return self._hydrate(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> JournalEntry | None:
        row = self._query_one(
            f"SELECT {_ENTRY_COLUMNS} FROM journal_entries WHERE operation_id=?",
            (operation_id,),
        )
        return self._hydrate(row) if row else None

    def list_unposted(self) -> list[JournalEntry]:
        return [self._hydrate(row) for row in self._query(
            f"SELECT {_ENTRY_COLUMNS} FROM journal_entries"
            " WHERE status IN ('DRAFT','VALIDATED') ORDER BY created_at")]

    def count_unposted(self, *, date_from: str, date_to: str) -> int:
        row = self._query_one(
            "SELECT COUNT(*) AS n FROM journal_entries WHERE status IN ('DRAFT','VALIDATED')"
            " AND posting_date BETWEEN ? AND ?", (date_from, date_to))
        return int(row["n"] or 0) if row else 0

    def account_balance(self, account_id: str, currency_code: str, *,
                        natural_debit: bool = True) -> Decimal:
        """Saldo contabilizado de una cuenta en su moneda (Decimal, nunca SUM SQL)."""
        debits = credits = Decimal("0")
        for row in self._query(
                "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
                " JOIN journal_entries je ON je.id = jl.journal_entry_id"
                " WHERE jl.account_id=? AND je.status IN ('POSTED','REVERSED')"
                " AND jl.currency_code=?", (account_id, currency_code)):
            debits += Decimal(str(row["debit_amount"] or "0"))
            credits += Decimal(str(row["credit_amount"] or "0"))
        return debits - credits if natural_debit else credits - debits

    def account_has_movements(self, account_id: str) -> bool:
        row = self._query_one(
            "SELECT 1 AS hit FROM journal_lines jl JOIN journal_entries je"
            " ON je.id = jl.journal_entry_id WHERE jl.account_id=?"
            " AND je.status IN ('POSTED','REVERSED') LIMIT 1", (account_id,))
        return row is not None

    def get_posted_line(self, journal_line_id: str) -> dict | None:
        """One journal line of a POSTED entry (read-model for reconciliation)."""
        return self._query_one(
            "SELECT jl.id, jl.account_id, jl.debit_amount, jl.credit_amount, jl.currency_code,"
            " je.posting_date, je.entry_number, je.description"
            " FROM journal_lines jl JOIN journal_entries je ON je.id=jl.journal_entry_id"
            " WHERE jl.id=? AND je.status='POSTED'",
            (journal_line_id,),
        )

    def exists_unbalanced(self) -> bool:
        """Debe = haber por asiento CONTABILIZADO, sumado en Decimal, en moneda
        de la operación y en moneda base (auditoría F20). Los borradores pueden
        estar descuadrados mientras se capturan: no cuentan."""
        totals: dict[str, list[Decimal]] = {}
        for row in self._query(
                "SELECT jl.journal_entry_id, jl.debit_amount, jl.credit_amount,"
                " jl.base_debit_amount, jl.base_credit_amount FROM journal_lines jl"
                " JOIN journal_entries je ON je.id = jl.journal_entry_id"
                " WHERE je.status IN ('VALIDATED','POSTED','REVERSED')"):
            acc = totals.setdefault(row["journal_entry_id"], [Decimal("0"), Decimal("0")])
            acc[0] += Decimal(str(row["debit_amount"] or "0")) - Decimal(
                str(row["credit_amount"] or "0"))
            acc[1] += Decimal(str(row["base_debit_amount"] or "0")) - Decimal(
                str(row["base_credit_amount"] or "0"))
        return any(trade != 0 or base != 0 for trade, base in totals.values())

    def _hydrate(self, row: dict) -> JournalEntry:
        base_currency = row["base_currency_code"]
        lines = [
            _line_to_entity(line_row, base_currency)
            for line_row in self._query(
                f"SELECT {_LINE_COLUMNS} FROM journal_lines"
                " WHERE journal_entry_id=? ORDER BY line_index",
                (row["id"],),
            )
        ]
        return JournalEntry(
            id=row["id"],
            journal_id=row["journal_id"],
            entry_number=row["entry_number"],
            entry_date=date.fromisoformat(row["entry_date"]),
            posting_date=date.fromisoformat(row["posting_date"]),
            fiscal_period_id=row["fiscal_period_id"],
            description=row["description"],
            currency_code=row["currency_code"],
            base_currency_code=base_currency,
            posting_reference=PostingReference(
                source_module=row["source_module"],
                source_document_id=row["source_document_id"],
                posting_purpose=PostingPurpose(row["posting_purpose"]),
                operation_id=row["operation_id"],
            ),
            source_document_type=row["source_document_type"],
            branch_id=row["branch_id"],
            status=JournalEntryStatus(row["status"]),
            reversal_of_entry_id=row["reversal_of_entry_id"],
            reversed_by_entry_id=row["reversed_by_entry_id"],
            created_by=row["created_by"],
            validated_by=row["validated_by"],
            validated_at=row["validated_at"],
            posted_by=row["posted_by"],
            posted_at=row["posted_at"],
            cancelled_by=row["cancelled_by"],
            cancel_reason=row["cancel_reason"],
            lines=lines,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
