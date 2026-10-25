"""Account entity — one node of the hierarchical chart of accounts (§8.1).

Reglas:
- No se contabiliza en cuentas agrupadoras (``posting_allowed = False``).
- Una cuenta con movimientos no cambia de tipo ni de naturaleza y no se elimina
  (no existe operación de borrado: se desactiva).
- Los saldos NO se guardan en la cuenta: siempre se derivan del mayor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import (
    NORMAL_BALANCE_BY_TYPE,
    AccountType,
    CashFlowCategory,
    NormalBalance,
)
from backend.domain.finance.exceptions import (
    AccountInactiveError,
    AccountInUseError,
    AccountNotPostableError,
    FinanceDomainError,
)
from backend.domain.finance.value_objects.account_code import AccountCode
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Account:
    id: str
    code: AccountCode
    name: str
    account_type: AccountType
    normal_balance: NormalBalance
    parent_account_id: str | None = None
    posting_allowed: bool = True
    reconciliation_required: bool = False
    currency_code: str = "MXN"
    branch_restriction_id: str | None = None
    cash_flow_category: CashFlowCategory = CashFlowCategory.NONE
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        account_type: AccountType,
        *,
        parent_account_id: str | None = None,
        posting_allowed: bool = True,
        reconciliation_required: bool = False,
        currency_code: str = "MXN",
        branch_restriction_id: str | None = None,
        cash_flow_category: CashFlowCategory = CashFlowCategory.NONE,
    ) -> "Account":
        if not name or not name.strip():
            raise FinanceDomainError("La cuenta requiere nombre")
        return cls(
            id=new_uuid(),
            code=AccountCode(code),
            name=name.strip(),
            account_type=account_type,
            normal_balance=NORMAL_BALANCE_BY_TYPE[account_type],
            parent_account_id=parent_account_id,
            posting_allowed=posting_allowed,
            reconciliation_required=reconciliation_required,
            currency_code=currency_code.upper(),
            branch_restriction_id=branch_restriction_id,
            cash_flow_category=cash_flow_category,
        )

    @property
    def is_summary(self) -> bool:
        return not self.posting_allowed

    def assert_postable(self, *, branch_id: str | None = None) -> None:
        if not self.active:
            raise AccountInactiveError(f"La cuenta {self.code} está inactiva")
        if not self.posting_allowed:
            raise AccountNotPostableError(
                f"La cuenta {self.code} es agrupadora; no admite movimientos")
        if self.branch_restriction_id and branch_id and branch_id != self.branch_restriction_id:
            raise AccountNotPostableError(
                f"La cuenta {self.code} sólo admite movimientos de su sucursal")

    def assert_can_be_parent_of(self, child: "Account") -> None:
        if self.posting_allowed:
            raise FinanceDomainError(
                f"La cuenta {self.code} admite movimientos; sólo una agrupadora tiene subcuentas")
        if self.account_type is not child.account_type:
            raise FinanceDomainError(
                f"La subcuenta {child.code} ({child.account_type.value}) no puede colgar de "
                f"{self.code} ({self.account_type.value}): conceptos incompatibles")
        if not child.code.is_descendant_of(self.code):
            raise FinanceDomainError(
                f"El código {child.code} no pertenece a la rama {self.code}")

    def update(self, *, name: str | None = None, reconciliation_required: bool | None = None,
               cash_flow_category: CashFlowCategory | None = None,
               account_type: AccountType | None = None, posting_allowed: bool | None = None,
               has_movements: bool) -> None:
        """Cambia atributos editables. Tipo, naturaleza y carácter agrupador de
        una cuenta con movimientos no cambian (reutilizarla para otro concepto
        rompería todos los saldos históricos)."""
        if account_type is not None and account_type is not self.account_type:
            if has_movements:
                raise AccountInUseError(
                    f"La cuenta {self.code} tiene movimientos: no cambia de tipo ni de naturaleza")
            self.account_type = account_type
            self.normal_balance = NORMAL_BALANCE_BY_TYPE[account_type]
        if posting_allowed is not None and posting_allowed != self.posting_allowed:
            if has_movements:
                raise AccountInUseError(
                    f"La cuenta {self.code} tiene movimientos: no puede volverse agrupadora")
            self.posting_allowed = posting_allowed
        if name is not None:
            if not name.strip():
                raise FinanceDomainError("La cuenta requiere nombre")
            self.name = name.strip()
        if reconciliation_required is not None:
            self.reconciliation_required = reconciliation_required
        if cash_flow_category is not None:
            self.cash_flow_category = cash_flow_category
        self.updated_at = _utcnow()

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self.updated_at = _utcnow()
