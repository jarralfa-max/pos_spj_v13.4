"""CreateAccountUseCase — adds one account to the chart of accounts."""

from __future__ import annotations

import json

from backend.domain.finance.entities.account import Account
from backend.domain.finance.enums import AccountType, CashFlowCategory
from backend.domain.finance.exceptions import FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class CreateAccountUseCase:
    def execute(
        self,
        connection,
        *,
        code: str,
        name: str,
        account_type: AccountType,
        parent_account_id: str | None = None,
        posting_allowed: bool = True,
        reconciliation_required: bool = False,
        cash_flow_category: CashFlowCategory = CashFlowCategory.NONE,
        currency_code: str = "MXN",
        operation_id: str,
    ) -> Account:
        with FinanceUnitOfWork(connection) as uow:
            if uow.accounts.get_by_code(code) is not None:
                raise FinanceDomainError(f"Ya existe una cuenta con código {code}")
            if parent_account_id is not None and uow.accounts.get(parent_account_id) is None:
                raise FinanceDomainError("La cuenta padre no existe")
            account = Account.create(
                code, name, account_type,
                parent_account_id=parent_account_id,
                posting_allowed=posting_allowed,
                reconciliation_required=reconciliation_required,
                cash_flow_category=cash_flow_category,
                currency_code=currency_code,
            )
            uow.accounts.save(account)
            uow.outbox.enqueue(
                event_id=new_uuid(),
                event_name=EventName.ACCOUNT_CREATED.value,
                payload_json=json.dumps({
                    "account_id": account.id,
                    "code": code,
                    "account_type": account_type.value,
                }),
                operation_id=operation_id,
            )
            return account
