"""Reglas compartidas por los casos de uso de Finanzas.

Nada aquí decide cuentas por texto libre: las cuentas salen de los perfiles
contables vigentes y de la cuenta espejo de cada cuenta de tesorería.
"""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import TreasuryAccountType
from backend.domain.finance.exceptions import (
    CurrencyMismatchError,
    FinanceDomainError,
    InsufficientTreasuryFundsError,
    PostingProfileNotFoundError,
    TreasuryAccountNotFoundError,
)
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork


def period_code(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def require_profile(uow: FinanceUnitOfWork, key: str, on_date: date, *,
                    branch_id: str | None = None, **criteria):
    profile = uow.posting_profiles.find_effective(key, on_date, branch_id=branch_id, **criteria)
    if profile is None:
        raise PostingProfileNotFoundError(
            f"No hay perfil contable {key} vigente al {on_date.isoformat()}")
    return profile


def require_treasury(uow: FinanceUnitOfWork, treasury_account_id: str, *,
                     currency_code: str | None = None,
                     money_only: bool = True) -> TreasuryAccount:
    account = uow.treasury.get(treasury_account_id) if treasury_account_id else None
    if account is None or not account.active:
        raise TreasuryAccountNotFoundError("La cuenta de tesorería no existe o está inactiva")
    if money_only and not account.holds_money:
        raise FinanceDomainError(
            "Un monedero promocional no es dinero; use el proceso de su instrumento")
    if currency_code is not None and account.currency_code != currency_code.upper():
        raise CurrencyMismatchError(
            f"La operación está en {currency_code} y la cuenta {account.name} en "
            f"{account.currency_code}; no se mezcla sin conversión explícita")
    return account


def assert_available_funds(uow: FinanceUnitOfWork, account: TreasuryAccount,
                           amount: Money) -> None:
    """Una salida no deja la cuenta en negativo salvo sobregiro pactado (§13).
    El saldo es el contable de su cuenta espejo, no una columna acumulada."""
    account.assert_can_disburse()
    if account.allows_overdraft:
        return
    balance = uow.treasury.ledger_balance(account.ledger_account_id, account.currency_code)
    if amount > balance:
        raise InsufficientTreasuryFundsError(
            f"Saldo insuficiente en {account.name}: disponible {balance.to_string()}, "
            f"requerido {amount.to_string()}")


#: Cuentas desde las que nunca se paga a un proveedor (BUGFIX skill FASE 12).
FORBIDDEN_SUPPLIER_PAYMENT_SOURCES = {
    TreasuryAccountType.CASH_REGISTER:
        "Las compras no se pagan desde Caja POS. Use Tesorería/Capital o CxP.",
    TreasuryAccountType.DIGITAL_WALLET:
        "Un monedero promocional no es dinero; no paga proveedores.",
}
