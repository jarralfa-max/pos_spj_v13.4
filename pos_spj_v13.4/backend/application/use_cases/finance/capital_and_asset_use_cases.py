"""Capital and fixed-asset use cases — contributions, CAPEX, depreciation, disposal."""

from __future__ import annotations

import json
from datetime import date

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.fixed_asset import FixedAsset
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.depreciation_service import DepreciationDomainService
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class RegisterCapitalContributionUseCase:
    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, amount: str, contribution_date: date,
                treasury_account_id: str, contributor: str = "",
                currency_code: str = "MXN", operation_id: str) -> str:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.journal_entries.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate.id
            treasury_account = uow.treasury.get(treasury_account_id)
            if treasury_account is None:
                raise FinanceDomainError("Cuenta de tesorería inexistente")
            money = Money.from_string(amount, currency_code)
            profile = uow.posting_profiles.find_effective("CAPITAL", contribution_date)
            if profile is None:
                raise FinanceDomainError("No hay perfil contable CAPITAL vigente")
            contribution_id = new_uuid()
            entry = self._engine.post(
                uow, JournalType.GENERAL, contribution_date,
                f"Aportación de capital {contributor}".strip(),
                PostingReference("finance", contribution_id,
                                 PostingPurpose.CAPITAL_CONTRIBUTION, operation_id),
                [
                    LineSpec(treasury_account.ledger_account_id, debit=money,
                             description="Entrada de capital"),
                    LineSpec(profile.account_for("capital_account_id"), credit=money,
                             description="Aportación de capital"),
                ],
            )
            uow.outbox.enqueue(
                event_id=new_uuid(),
                event_name=EventName.CAPITAL_CONTRIBUTION_REGISTERED.value,
                payload_json=json.dumps({
                    "contribution_id": contribution_id, "journal_entry_id": entry.id,
                    "amount": money.to_string(),
                }),
                operation_id=new_uuid(),
            )
            return entry.id


class CapitalizeAssetUseCase:
    """Registers a fixed asset (CAPEX) and posts Dr asset / Cr bank-or-payable."""

    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, name: str, acquisition_cost: str,
                residual_value: str = "0.00", useful_life_months: int,
                capitalization_date: date, paid_from_treasury_account_id: str | None = None,
                branch_id: str | None = None, cost_center_id: str | None = None,
                currency_code: str = "MXN", operation_id: str) -> FixedAsset:
        with FinanceUnitOfWork(connection) as uow:
            duplicate = uow.fixed_assets.find_by_operation_id(operation_id)
            if duplicate is not None:
                return duplicate
            profile = uow.posting_profiles.find_effective("FIXED_ASSET", capitalization_date)
            if profile is None:
                raise FinanceDomainError("No hay perfil contable FIXED_ASSET vigente")
            cost = Money.from_string(acquisition_cost, currency_code)
            asset = FixedAsset.create(
                name, cost, Money.from_string(residual_value, currency_code),
                useful_life_months, operation_id,
                branch_id=branch_id, cost_center_id=cost_center_id,
            )
            asset.capitalize(
                capitalization_date,
                profile.account_for("asset_account_id"),
                profile.account_for("depreciation_expense_account_id"),
                profile.account_for("accumulated_depreciation_account_id"),
            )
            if paid_from_treasury_account_id:
                treasury_account = uow.treasury.get(paid_from_treasury_account_id)
                if treasury_account is None:
                    raise FinanceDomainError("Cuenta de tesorería inexistente")
                credit_account = treasury_account.ledger_account_id
            else:
                credit_account = profile.account_for("payable_account_id")
            self._engine.post(
                uow, JournalType.FIXED_ASSETS, capitalization_date,
                f"Capitalización de activo {name}",
                PostingReference("finance", asset.id,
                                 PostingPurpose.ASSET_CAPITALIZATION, new_uuid()),
                [
                    LineSpec(asset.asset_account_id, debit=cost,
                             description=f"Alta de activo {name}"),
                    LineSpec(credit_account, credit=cost,
                             description="Origen de fondos CAPEX"),
                ],
                currency_code=currency_code, branch_id=branch_id,
            )
            uow.fixed_assets.save(asset)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name=EventName.FIXED_ASSET_CAPITALIZED.value,
                payload_json=json.dumps({"asset_id": asset.id, "name": name,
                                         "cost": cost.to_string()}),
                operation_id=operation_id,
            )
            return asset


class RunDepreciationUseCase:
    """Posts one straight-line depreciation entry per asset for a period.
    Double depreciation of the same period is structurally impossible."""

    def __init__(self) -> None:
        self._engine = PostingEngine()
        self._domain = DepreciationDomainService()

    def execute(self, connection, *, year: int, month: int, operation_id: str) -> list[str]:
        period_code = f"{year:04d}-{month:02d}"
        entry_date = date(year, month, 28)
        posted: list[str] = []
        with FinanceUnitOfWork(connection) as uow:
            assets = self._domain.depreciable_assets(
                uow.fixed_assets.list_capitalized(), period_code,
            )
            for asset in assets:
                amount = self._domain.apply(asset, period_code)
                if amount.is_zero():
                    continue
                entry = self._engine.post(
                    uow, JournalType.FIXED_ASSETS, entry_date,
                    f"Depreciación {period_code} — {asset.name}",
                    PostingReference("finance", f"{asset.id}:{period_code}",
                                     PostingPurpose.DEPRECIATION, new_uuid()),
                    [
                        LineSpec(asset.depreciation_expense_account_id, debit=amount,
                                 description=f"Gasto por depreciación {asset.name}"),
                        LineSpec(asset.accumulated_depreciation_account_id, credit=amount,
                                 description="Depreciación acumulada"),
                    ],
                    branch_id=asset.branch_id,
                )
                uow.fixed_assets.update(asset)
                posted.append(entry.id)
            if posted:
                uow.outbox.enqueue(
                    event_id=new_uuid(), event_name=EventName.DEPRECIATION_POSTED.value,
                    payload_json=json.dumps({"period": period_code, "entries": len(posted)}),
                    operation_id=operation_id,
                )
        return posted


class DisposeAssetUseCase:
    """Disposal: removes cost and accumulated depreciation; the net book value
    becomes an other-expense (loss) — proceeds handling can extend this later."""

    def __init__(self) -> None:
        self._engine = PostingEngine()

    def execute(self, connection, *, asset_id: str, disposal_date: date,
                operation_id: str) -> str:
        with FinanceUnitOfWork(connection) as uow:
            asset = uow.fixed_assets.get(asset_id)
            if asset is None:
                raise FinanceDomainError("El activo no existe")
            if asset.disposal_journal_entry_id:
                return asset.disposal_journal_entry_id
            profile = uow.posting_profiles.find_effective("INVENTORY", disposal_date)
            loss_account = None
            fixed_profile = uow.posting_profiles.find_effective("FIXED_ASSET", disposal_date)
            if fixed_profile is None or profile is None:
                raise FinanceDomainError("Faltan perfiles contables vigentes")
            loss_account = fixed_profile.account_for("depreciation_expense_account_id")

            lines = []
            if asset.accumulated_depreciation.is_positive():
                lines.append(LineSpec(asset.accumulated_depreciation_account_id,
                                      debit=asset.accumulated_depreciation,
                                      description="Cancelación de depreciación acumulada"))
            nbv = asset.net_book_value()
            if nbv.is_positive():
                lines.append(LineSpec(loss_account, debit=nbv,
                                      description="Pérdida por disposición"))
            lines.append(LineSpec(asset.asset_account_id, credit=asset.acquisition_cost,
                                  description=f"Baja de activo {asset.name}"))
            entry = self._engine.post(
                uow, JournalType.FIXED_ASSETS, disposal_date,
                f"Disposición de activo {asset.name}",
                PostingReference("finance", asset.id, PostingPurpose.ASSET_DISPOSAL,
                                 operation_id),
                lines, branch_id=asset.branch_id,
            )
            asset.dispose(disposal_date, entry.id)
            uow.fixed_assets.update(asset)
            return entry.id
