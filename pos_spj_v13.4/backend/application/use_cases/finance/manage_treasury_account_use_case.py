"""Alta y mantenimiento de cuentas de tesorería (§13).

Cada cuenta de tesorería tiene una cuenta ESPEJO del mayor (activo
contabilizable) de la que salen sus saldos. Del número de cuenta sólo se
guarda la forma enmascarada (§25).
"""

from __future__ import annotations

from backend.domain.finance.entities.audit_record import mask_account_number
from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import AccountType, AuditAction, TreasuryAccountType
from backend.domain.finance.exceptions import (
    AccountNotFoundError,
    FinanceDomainError,
    TreasuryAccountNotFoundError,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


def _snapshot(account: TreasuryAccount) -> dict:
    return {"name": account.name, "account_type": account.account_type.value,
            "masked_account_number": account.masked_account_number,
            "restricted": account.restricted, "allows_overdraft": account.allows_overdraft,
            "active": account.active}


class ManageTreasuryAccountUseCase:
    def create(self, connection, *, name: str, account_type: TreasuryAccountType,
               ledger_account_id: str, operation_id: str, created_by: str,
               currency_code: str = "MXN", branch_id: str | None = None,
               bank_name: str | None = None, account_number: str | None = None,
               restricted: bool = False, allows_overdraft: bool = False) -> TreasuryAccount:
        with FinanceUnitOfWork(connection) as uow:
            ledger = uow.accounts.get(ledger_account_id)
            if ledger is None:
                raise AccountNotFoundError("La cuenta espejo del mayor no existe")
            if ledger.account_type is not AccountType.ASSET:
                raise FinanceDomainError("La cuenta espejo de tesorería es una cuenta de activo")
            ledger.assert_postable()
            if ledger.currency_code != currency_code.upper():
                raise FinanceDomainError("La cuenta espejo está en otra moneda")
            account = TreasuryAccount.create(
                name, account_type, ledger_account_id, currency_code=currency_code,
                branch_id=branch_id, bank_name=bank_name, account_number=account_number,
                restricted=restricted, allows_overdraft=allows_overdraft)
            uow.treasury.save(account)
            uow.audit(AuditAction.TREASURY_MOVEMENT, entity_type="treasury_account",
                      entity_id=account.id, operation_id=operation_id, user_id=created_by,
                      after=_snapshot(account), branch_id=branch_id)
            return account

    def update(self, connection, *, treasury_account_id: str, operation_id: str,
               updated_by: str, name: str | None = None, restricted: bool | None = None,
               allows_overdraft: bool | None = None, active: bool | None = None,
               bank_name: str | None = None, account_number: str | None = None,
               reason: str | None = None) -> TreasuryAccount:
        with FinanceUnitOfWork(connection) as uow:
            account = uow.treasury.get(treasury_account_id)
            if account is None:
                raise TreasuryAccountNotFoundError("La cuenta de tesorería no existe")
            before = _snapshot(account)
            if name is not None:
                if not name.strip():
                    raise FinanceDomainError("La cuenta de tesorería requiere nombre")
                account.name = name.strip()
            if bank_name is not None:
                account.bank_name = bank_name.strip() or None
            if account_number is not None:
                account.masked_account_number = mask_account_number(account_number)
            if restricted is not None:
                account.restricted = bool(restricted)
            if allows_overdraft is not None:
                account.allows_overdraft = bool(allows_overdraft)
            if active is not None:
                account.active = bool(active)
            uow.treasury.update(account)
            uow.audit(AuditAction.TREASURY_MOVEMENT, entity_type="treasury_account",
                      entity_id=account.id, operation_id=operation_id, user_id=updated_by,
                      before=before, after=_snapshot(account), reason=reason,
                      branch_id=account.branch_id)
            return account
