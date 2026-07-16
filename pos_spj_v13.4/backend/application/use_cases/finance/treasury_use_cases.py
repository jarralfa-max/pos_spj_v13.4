"""Treasury use cases — transfers between treasury accounts and statement import."""

from __future__ import annotations

import json
from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.bank_statement import BankStatement
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.policies.reconciliation_policy import ReconciliationPolicy
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.services.treasury_service import TreasuryService
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class RegisterTreasuryTransferUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()
        self._domain = TreasuryService()

    def execute(self, connection, *, source_treasury_account_id: str,
                target_treasury_account_id: str, amount: str, transfer_date: date,
                reference: str = "", operation_id: str) -> str:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.journal_entries.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate.id
            source = uow.treasury.get(source_treasury_account_id)
            target = uow.treasury.get(target_treasury_account_id)
            if source is None or target is None:
                raise FinanceDomainError("Cuenta de tesorería inexistente")
            money = Money.from_string(amount, source.currency_code)
            self._domain.validate_transfer(source, target, money)
            transfer_id = new_uuid()
            entry = self._engine.post(
                uow, JournalType.BANK, transfer_date,
                f"Transferencia {source.name} → {target.name}",
                PostingReference("finance", transfer_id, PostingPurpose.TREASURY_TRANSFER,
                                 operation_id),
                [
                    LineSpec(target.ledger_account_id, debit=money,
                             description=f"Entrada por transferencia {reference}"),
                    LineSpec(source.ledger_account_id, credit=money,
                             description=f"Salida por transferencia {reference}"),
                ],
            )
            uow.outbox.enqueue(
                event_id=new_uuid(),
                event_name=EventName.TREASURY_TRANSFER_REGISTERED.value,
                payload_json=json.dumps({
                    "transfer_id": transfer_id, "journal_entry_id": entry.id,
                    "amount": money.to_string(),
                    "source": source.id, "target": target.id,
                }),
                operation_id=new_uuid(),
            )
            return entry.id


class ImportBankStatementUseCase:
    def execute(self, connection, *, treasury_account_id: str, statement_date: date,
                opening_balance: str, closing_balance: str,
                lines: list[dict], operation_id: str) -> BankStatement:
        """``lines``: [{"transaction_date": "YYYY-MM-DD", "description": str,
        "amount": "signed decimal string", "external_reference": str}]"""
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.treasury.find_statement_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            account = uow.treasury.get(treasury_account_id)
            if account is None:
                raise FinanceDomainError("Cuenta de tesorería inexistente")
            currency = account.currency_code
            statement = BankStatement.create(
                treasury_account_id, statement_date,
                Money.from_string(opening_balance, currency),
                Money.from_string(closing_balance, currency),
                operation_id,
            )
            for line in lines:
                statement.add_line(
                    date.fromisoformat(str(line["transaction_date"])),
                    str(line.get("description") or ""),
                    Money.from_string(str(line["amount"]), currency),
                    external_reference=str(line.get("external_reference") or ""),
                )
            ReconciliationPolicy().enforce_statement_consistency(statement)
            uow.treasury.save_statement(statement)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.BANK_STATEMENT_IMPORTED.value,
                payload_json=json.dumps({
                    "bank_statement_id": statement.id,
                    "treasury_account_id": treasury_account_id,
                    "lines": len(statement.lines),
                }),
                operation_id=operation_id,
            )
            return statement
