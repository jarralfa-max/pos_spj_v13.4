"""TreasuryAccount entity — bank, cash, processor and clearing accounts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import TreasuryAccountType
from backend.domain.finance.exceptions import FinanceDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class TreasuryAccount:
    id: str
    name: str
    account_type: TreasuryAccountType
    ledger_account_id: str
    currency_code: str = "MXN"
    branch_id: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    requires_reconciliation: bool = False
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, name: str, account_type: TreasuryAccountType, ledger_account_id: str,
               *, currency_code: str = "MXN", branch_id: str | None = None,
               bank_name: str | None = None, bank_account_number: str | None = None,
               requires_reconciliation: bool | None = None) -> "TreasuryAccount":
        if not name or not name.strip():
            raise FinanceDomainError("TreasuryAccount.name is required")
        if not ledger_account_id:
            raise FinanceDomainError("TreasuryAccount requires its ledger_account_id (GL mirror)")
        if requires_reconciliation is None:
            requires_reconciliation = account_type in (
                TreasuryAccountType.BANK,
                TreasuryAccountType.PAYMENT_PROCESSOR,
                TreasuryAccountType.CLEARING_ACCOUNT,
            )
        return cls(
            id=new_uuid(), name=name.strip(), account_type=account_type,
            ledger_account_id=ledger_account_id, currency_code=currency_code,
            branch_id=branch_id, bank_name=bank_name,
            bank_account_number=bank_account_number,
            requires_reconciliation=requires_reconciliation,
        )
