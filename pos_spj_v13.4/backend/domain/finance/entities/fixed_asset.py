"""FixedAsset entity — CAPEX, capitalization, depreciation and disposal (§17).

Estados: DRAFT → ACTIVE ⇄ SUSPENDED → DISPOSED | SOLD | WRITTEN_OFF.
La depreciación acumulada sólo cambia por una corrida registrada (``register_depreciation``
recibe la corrida); nunca se escribe directamente. Un activo totalmente
depreciado sigue ACTIVO (en uso) con valor en libros igual al residual.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.finance.enums import DepreciationMethod, FixedAssetStatus
from backend.domain.finance.exceptions import AssetNotActiveError, FinanceDomainError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Estados terminales (el activo ya salió del patrimonio).
RETIRED_STATUSES = frozenset({FixedAssetStatus.DISPOSED, FixedAssetStatus.SOLD,
                              FixedAssetStatus.WRITTEN_OFF})


@dataclass(slots=True)
class FixedAssetCategory:
    """Categoría contable: cuentas y vida útil sugerida de sus activos."""

    id: str
    code: str
    name: str
    asset_account_id: str
    depreciation_expense_account_id: str
    accumulated_depreciation_account_id: str
    default_useful_life_months: int | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, code: str, name: str, *, asset_account_id: str,
               depreciation_expense_account_id: str,
               accumulated_depreciation_account_id: str,
               default_useful_life_months: int | None = None) -> "FixedAssetCategory":
        code = (code or "").strip().upper()
        if not code or not (name or "").strip():
            raise FinanceDomainError("La categoría de activo requiere código y nombre")
        if default_useful_life_months is not None and default_useful_life_months <= 0:
            raise FinanceDomainError("La vida útil sugerida debe ser mayor que cero")
        return cls(id=new_uuid(), code=code, name=name.strip(),
                   asset_account_id=asset_account_id,
                   depreciation_expense_account_id=depreciation_expense_account_id,
                   accumulated_depreciation_account_id=accumulated_depreciation_account_id,
                   default_useful_life_months=default_useful_life_months)


@dataclass(slots=True)
class FixedAsset:
    id: str
    name: str
    acquisition_cost: Money
    residual_value: Money
    useful_life_months: int
    capitalization_date: date | None
    operation_id: str
    accumulated_depreciation: Money = None  # type: ignore[assignment]
    depreciation_method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE
    status: FixedAssetStatus = FixedAssetStatus.DRAFT
    asset_account_id: str | None = None
    depreciation_expense_account_id: str | None = None
    accumulated_depreciation_account_id: str | None = None
    last_depreciated_period: str | None = None   # "YYYY-MM"
    disposal_date: date | None = None
    disposal_journal_entry_id: str | None = None
    branch_id: str | None = None
    cost_center_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    asset_code: str = ""
    asset_category_id: str | None = None
    acquisition_date: date | None = None
    supplier_id: str | None = None
    source_document_id: str | None = None
    project_id: str | None = None
    status_reason: str | None = None

    def __post_init__(self) -> None:
        if self.accumulated_depreciation is None:
            self.accumulated_depreciation = Money.zero(self.acquisition_cost.currency_code)

    @classmethod
    def create(cls, name: str, acquisition_cost: Money, residual_value: Money,
               useful_life_months: int, operation_id: str, *,
               asset_code: str = "", asset_category_id: str | None = None,
               acquisition_date: date | None = None, supplier_id: str | None = None,
               source_document_id: str | None = None, project_id: str | None = None,
               branch_id: str | None = None, cost_center_id: str | None = None) -> "FixedAsset":
        if not name or not name.strip():
            raise FinanceDomainError("El activo requiere nombre")
        if not acquisition_cost.is_positive():
            raise FinanceDomainError("El costo de adquisición debe ser mayor que cero")
        if residual_value.is_negative() or residual_value > acquisition_cost:
            raise FinanceDomainError("El valor residual va de cero al costo de adquisición")
        if useful_life_months <= 0:
            raise FinanceDomainError("La vida útil debe ser mayor que cero")
        return cls(
            id=new_uuid(), name=name.strip(), acquisition_cost=acquisition_cost,
            residual_value=residual_value, useful_life_months=useful_life_months,
            capitalization_date=None, operation_id=operation_id,
            asset_code=(asset_code or "").strip().upper(),
            asset_category_id=asset_category_id, acquisition_date=acquisition_date,
            supplier_id=supplier_id, source_document_id=source_document_id,
            project_id=project_id, branch_id=branch_id, cost_center_id=cost_center_id,
        )

    # ── ciclo de vida ────────────────────────────────────────────────────
    @property
    def in_service_date(self) -> date | None:
        return self.capitalization_date

    def capitalize(self, capitalization_date: date, asset_account_id: str,
                   depreciation_expense_account_id: str,
                   accumulated_depreciation_account_id: str) -> None:
        if self.status is not FixedAssetStatus.DRAFT:
            raise FinanceDomainError(f"No se capitaliza un activo {self.status.value}")
        if self.acquisition_date is not None and capitalization_date < self.acquisition_date:
            raise FinanceDomainError("La puesta en servicio no puede ser anterior a la adquisición")
        self.capitalization_date = capitalization_date
        if self.acquisition_date is None:
            self.acquisition_date = capitalization_date
        self.asset_account_id = asset_account_id
        self.depreciation_expense_account_id = depreciation_expense_account_id
        self.accumulated_depreciation_account_id = accumulated_depreciation_account_id
        self.status = FixedAssetStatus.ACTIVE
        self.updated_at = _utcnow()

    def suspend(self, reason: str) -> None:
        if self.status is not FixedAssetStatus.ACTIVE:
            raise AssetNotActiveError(f"Sólo se suspende un activo activo ({self.status.value})")
        if not (reason or "").strip():
            raise FinanceDomainError("Suspender un activo exige el motivo")
        self.status = FixedAssetStatus.SUSPENDED
        self.status_reason = reason.strip()
        self.updated_at = _utcnow()

    def resume(self) -> None:
        if self.status is not FixedAssetStatus.SUSPENDED:
            raise FinanceDomainError(f"Sólo se reanuda un activo suspendido ({self.status.value})")
        self.status = FixedAssetStatus.ACTIVE
        self.status_reason = None
        self.updated_at = _utcnow()

    def retire(self, status: FixedAssetStatus, retirement_date: date, journal_entry_id: str,
               reason: str = "") -> None:
        """Baja (DISPOSED), venta (SOLD) o castigo (WRITTEN_OFF)."""
        if status not in RETIRED_STATUSES:
            raise FinanceDomainError(f"{status.value} no es un estado de baja")
        if self.status not in (FixedAssetStatus.ACTIVE, FixedAssetStatus.SUSPENDED):
            raise AssetNotActiveError(f"No se da de baja un activo {self.status.value}")
        self.status = status
        self.disposal_date = retirement_date
        self.disposal_journal_entry_id = journal_entry_id
        self.status_reason = (reason or "").strip() or None
        self.updated_at = _utcnow()

    def dispose(self, disposal_date: date, journal_entry_id: str) -> None:
        self.retire(FixedAssetStatus.DISPOSED, disposal_date, journal_entry_id)

    # ── depreciación ─────────────────────────────────────────────────────
    def depreciable_base(self) -> Money:
        return self.acquisition_cost.subtract(self.residual_value)

    def monthly_depreciation(self) -> Money:
        base = self.depreciable_base()
        return Money(base.amount / Decimal(self.useful_life_months), base.currency_code)

    def remaining_depreciable(self) -> Money:
        return self.depreciable_base().subtract(self.accumulated_depreciation)

    @property
    def is_fully_depreciated(self) -> bool:
        return self.remaining_depreciable().is_zero()

    def register_depreciation(self, amount: Money, period_code: str) -> None:
        if self.status is not FixedAssetStatus.ACTIVE:
            raise AssetNotActiveError(f"No se deprecia un activo {self.status.value}")
        if self.last_depreciated_period is not None and period_code <= self.last_depreciated_period:
            raise FinanceDomainError(
                f"El periodo {period_code} ya se depreció (último: {self.last_depreciated_period})")
        if amount > self.remaining_depreciable():
            raise FinanceDomainError("La depreciación excede la base depreciable restante")
        self.accumulated_depreciation = self.accumulated_depreciation.add(amount)
        self.last_depreciated_period = period_code
        self.updated_at = _utcnow()

    def net_book_value(self) -> Money:
        return self.acquisition_cost.subtract(self.accumulated_depreciation)

    @property
    def book_value(self) -> Money:
        return self.net_book_value()
