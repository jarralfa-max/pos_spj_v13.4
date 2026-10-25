"""TreasuryAccount entity — bank, cash, processor and clearing accounts (§13).

Tesorería está separada de Contabilidad: la cuenta de tesorería es el
instrumento (banco, caja, terminal, monedero) y su ``ledger_account_id`` es la
cuenta espejo del mayor de la que salen sus saldos. No se guarda el número de
cuenta completo (§25): sólo su forma enmascarada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.entities.audit_record import mask_account_number
from backend.domain.finance.enums import TreasuryAccountType
from backend.domain.finance.exceptions import FinanceDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Tipos de tesorería que guardan dinero real (un monedero promocional no lo es).
MONEY_TREASURY_TYPES = frozenset({
    TreasuryAccountType.BANK, TreasuryAccountType.CASH_REGISTER,
    TreasuryAccountType.PETTY_CASH, TreasuryAccountType.GENERAL_CASH,
    TreasuryAccountType.PAYMENT_PROCESSOR, TreasuryAccountType.CLEARING_ACCOUNT,
})


@dataclass(slots=True)
class TreasuryAccount:
    id: str
    name: str
    account_type: TreasuryAccountType
    ledger_account_id: str
    currency_code: str = "MXN"
    branch_id: str | None = None
    bank_name: str | None = None
    masked_account_number: str = ""
    requires_reconciliation: bool = False
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    #: Fondos restringidos: no se usan para pagos ni transferencias de salida.
    restricted: bool = False
    #: Permite saldo negativo (línea de crédito / sobregiro pactado).
    allows_overdraft: bool = False

    @classmethod
    def create(cls, name: str, account_type: TreasuryAccountType, ledger_account_id: str,
               *, currency_code: str = "MXN", branch_id: str | None = None,
               bank_name: str | None = None, account_number: str | None = None,
               requires_reconciliation: bool | None = None, restricted: bool = False,
               allows_overdraft: bool = False) -> "TreasuryAccount":
        if not name or not name.strip():
            raise FinanceDomainError("La cuenta de tesorería requiere nombre")
        if not ledger_account_id:
            raise FinanceDomainError("La cuenta de tesorería requiere su cuenta espejo del mayor")
        if requires_reconciliation is None:
            requires_reconciliation = account_type in (
                TreasuryAccountType.BANK,
                TreasuryAccountType.PAYMENT_PROCESSOR,
                TreasuryAccountType.CLEARING_ACCOUNT,
            )
        return cls(
            id=new_uuid(), name=name.strip(), account_type=account_type,
            ledger_account_id=ledger_account_id, currency_code=currency_code.upper(),
            branch_id=branch_id, bank_name=(bank_name or "").strip() or None,
            masked_account_number=mask_account_number(account_number),
            requires_reconciliation=requires_reconciliation,
            restricted=bool(restricted), allows_overdraft=bool(allows_overdraft),
        )

    @property
    def holds_money(self) -> bool:
        return self.account_type in MONEY_TREASURY_TYPES

    def assert_can_disburse(self) -> None:
        if not self.active:
            raise FinanceDomainError(f"La cuenta {self.name} está inactiva")
        if self.restricted:
            raise FinanceDomainError(
                f"La cuenta {self.name} tiene fondos restringidos; no se dispone de ella")
