"""UpdateAccountUseCase — edita o desactiva una cuenta (§8.1).

Una cuenta con movimientos no cambia de tipo ni de naturaleza ni se vuelve
agrupadora; ninguna cuenta se elimina (se desactiva y queda su historia).
"""

from __future__ import annotations

from backend.domain.finance.enums import AccountType, AuditAction, CashFlowCategory
from backend.domain.finance.exceptions import AccountNotFoundError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


def _snapshot(account) -> dict:
    return {"name": account.name, "account_type": account.account_type.value,
            "posting_allowed": account.posting_allowed, "active": account.active,
            "reconciliation_required": account.reconciliation_required,
            "cash_flow_category": account.cash_flow_category.value}


class UpdateAccountUseCase:
    def execute(self, connection, *, account_id: str, operation_id: str,
                updated_by: str | None = None, name: str | None = None,
                account_type: AccountType | None = None, posting_allowed: bool | None = None,
                reconciliation_required: bool | None = None,
                cash_flow_category: CashFlowCategory | None = None,
                active: bool | None = None, reason: str | None = None):
        with FinanceUnitOfWork(connection) as uow:
            account = uow.accounts.get(account_id)
            if account is None:
                raise AccountNotFoundError("La cuenta no existe")
            before = _snapshot(account)
            has_movements = uow.journal_entries.account_has_movements(account_id)
            account.update(name=name, account_type=account_type,
                           posting_allowed=posting_allowed,
                           reconciliation_required=reconciliation_required,
                           cash_flow_category=cash_flow_category,
                           has_movements=has_movements)
            if active is False:
                account.deactivate()
            elif active is True:
                account.activate()
            uow.accounts.update(account)
            uow.audit(AuditAction.ACCOUNT_UPDATED, entity_type="account", entity_id=account.id,
                      operation_id=operation_id, user_id=updated_by, before=before,
                      after=_snapshot(account), reason=reason)
            return account
