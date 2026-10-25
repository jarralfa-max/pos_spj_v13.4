"""CreateAccountUseCase — adds one account to the hierarchical chart (§8.1)."""

from __future__ import annotations

from backend.application.services.finance.posting_engine import publish_finance_event
from backend.domain.finance.entities.account import Account
from backend.domain.finance.enums import AccountType, AuditAction, CashFlowCategory
from backend.domain.finance.exceptions import AccountNotFoundError, FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName


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
        branch_restriction_id: str | None = None,
        operation_id: str,
        created_by: str | None = None,
    ) -> Account:
        with FinanceUnitOfWork(connection) as uow:
            if uow.accounts.get_by_code(code) is not None:
                raise FinanceDomainError(f"Ya existe una cuenta con código {code}")
            account = Account.create(
                code, name, account_type,
                parent_account_id=parent_account_id,
                posting_allowed=posting_allowed,
                reconciliation_required=reconciliation_required,
                cash_flow_category=cash_flow_category,
                currency_code=currency_code,
                branch_restriction_id=branch_restriction_id,
            )
            if parent_account_id is not None:
                parent = uow.accounts.get(parent_account_id)
                if parent is None:
                    raise AccountNotFoundError("La cuenta padre no existe")
                parent.assert_can_be_parent_of(account)
            uow.accounts.save(account)
            uow.audit(AuditAction.ACCOUNT_CREATED, entity_type="account", entity_id=account.id,
                      operation_id=operation_id, user_id=created_by,
                      after={"code": code, "name": account.name,
                             "account_type": account_type.value,
                             "posting_allowed": posting_allowed})
            publish_finance_event(uow, EventName.ACCOUNT_CREATED, {
                "account_id": account.id, "code": code, "account_type": account_type.value,
            }, operation_id=operation_id, entity_id=account.id)
            return account
