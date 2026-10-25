"""ImportBankStatementUseCase — importación de estados de cuenta (§15).

Las partidas llegan ya leídas (CSV, XLSX o captura controlada; el lector vive
en infraestructura). El estado debe cuadrar (saldo inicial + partidas = saldo
final) y su huella de contenido es única por cuenta: importar el mismo estado
dos veces se rechaza con ``BankStatementAlreadyImportedError``.
"""

from __future__ import annotations

from datetime import date

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.application.use_cases.finance._support import require_treasury
from backend.domain.finance.entities.bank_statement import BankStatement
from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import BankStatementAlreadyImportedError
from backend.domain.finance.policies.reconciliation_policy import ReconciliationPolicy
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


class ImportBankStatementUseCase:
    def execute(self, connection, *, treasury_account_id: str, statement_date: date,
                opening_balance: str, closing_balance: str, lines: list[dict],
                operation_id: str, imported_by: str | None = None,
                source_format: str = "MANUAL", file_name: str = "") -> BankStatement:
        """``lines``: [{"transaction_date": "YYYY-MM-DD", "description": str,
        "amount": "signed decimal string", "external_reference": str}]"""
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.treasury.find_statement_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            account = require_treasury(uow, treasury_account_id, money_only=False)
            currency = account.currency_code
            statement = BankStatement.create(
                account.id, statement_date, Money.from_string(opening_balance, currency),
                Money.from_string(closing_balance, currency), operation_id,
                source_format=source_format, file_name=file_name, imported_by=imported_by)
            for line in lines:
                statement.add_line(
                    date.fromisoformat(str(line["transaction_date"])[:10]),
                    str(line.get("description") or ""),
                    Money.from_string(str(line["amount"]), currency),
                    external_reference=str(line.get("external_reference") or ""),
                )
            ReconciliationPolicy().enforce_statement_consistency(statement)
            seal = statement.seal()
            if uow.treasury.find_statement_by_hash(account.id, seal) is not None:
                raise BankStatementAlreadyImportedError(
                    "Ese estado de cuenta ya se importó para esta cuenta (mismo contenido)")
            uow.treasury.save_statement(statement)
            uow.audit(AuditAction.STATEMENT_IMPORTED, entity_type="bank_statement",
                      entity_id=statement.id, operation_id=operation_id, user_id=imported_by,
                      after={"treasury_account_id": account.id, "lines": len(statement.lines),
                             "statement_date": statement_date.isoformat(),
                             "source_format": statement.source_format,
                             "file_name": statement.file_name},
                      branch_id=account.branch_id)
            publish_finance_event(uow, EventName.BANK_STATEMENT_IMPORTED, {
                "bank_statement_id": statement.id, "treasury_account_id": account.id,
                "lines": len(statement.lines),
            }, operation_id=operation_id, entity_id=statement.id, branch_id=account.branch_id)
            return statement
