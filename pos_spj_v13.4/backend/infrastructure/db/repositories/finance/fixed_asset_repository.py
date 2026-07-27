"""FixedAsset repository."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.fixed_asset import FixedAsset
from backend.domain.finance.enums import DepreciationMethod, FixedAssetStatus
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, name, acquisition_cost, residual_value, accumulated_depreciation,"
            " currency_code, useful_life_months, depreciation_method, status,"
            " capitalization_date, asset_account_id, depreciation_expense_account_id,"
            " accumulated_depreciation_account_id, last_depreciated_period, disposal_date,"
            " disposal_journal_entry_id, branch_id, cost_center_id, operation_id,"
            " created_at, updated_at")


def _to_entity(row: dict) -> FixedAsset:
    currency = row["currency_code"]
    return FixedAsset(
        id=row["id"], name=row["name"],
        acquisition_cost=Money.from_string(row["acquisition_cost"], currency),
        residual_value=Money.from_string(row["residual_value"], currency),
        accumulated_depreciation=Money.from_string(row["accumulated_depreciation"], currency),
        useful_life_months=row["useful_life_months"],
        depreciation_method=DepreciationMethod(row["depreciation_method"]),
        status=FixedAssetStatus(row["status"]),
        capitalization_date=(date.fromisoformat(row["capitalization_date"])
                             if row["capitalization_date"] else None),
        asset_account_id=row["asset_account_id"],
        depreciation_expense_account_id=row["depreciation_expense_account_id"],
        accumulated_depreciation_account_id=row["accumulated_depreciation_account_id"],
        last_depreciated_period=row["last_depreciated_period"],
        disposal_date=date.fromisoformat(row["disposal_date"]) if row["disposal_date"] else None,
        disposal_journal_entry_id=row["disposal_journal_entry_id"],
        branch_id=row["branch_id"], cost_center_id=row["cost_center_id"],
        operation_id=row["operation_id"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class FixedAssetRepository(FinanceRepositoryBase):
    def save(self, asset: FixedAsset) -> None:
        self._execute(
            f"INSERT INTO fixed_assets ({_COLUMNS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (asset.id, asset.name, asset.acquisition_cost.to_string(),
             asset.residual_value.to_string(), asset.accumulated_depreciation.to_string(),
             asset.acquisition_cost.currency_code, asset.useful_life_months,
             asset.depreciation_method.value, asset.status.value,
             asset.capitalization_date.isoformat() if asset.capitalization_date else None,
             asset.asset_account_id, asset.depreciation_expense_account_id,
             asset.accumulated_depreciation_account_id, asset.last_depreciated_period,
             asset.disposal_date.isoformat() if asset.disposal_date else None,
             asset.disposal_journal_entry_id, asset.branch_id, asset.cost_center_id,
             asset.operation_id, asset.created_at, asset.updated_at),
        )

    def update(self, asset: FixedAsset) -> None:
        self._execute(
            "UPDATE fixed_assets SET accumulated_depreciation=?, status=?,"
            " capitalization_date=?, asset_account_id=?, depreciation_expense_account_id=?,"
            " accumulated_depreciation_account_id=?, last_depreciated_period=?,"
            " disposal_date=?, disposal_journal_entry_id=?, updated_at=? WHERE id=?",
            (asset.accumulated_depreciation.to_string(), asset.status.value,
             asset.capitalization_date.isoformat() if asset.capitalization_date else None,
             asset.asset_account_id, asset.depreciation_expense_account_id,
             asset.accumulated_depreciation_account_id, asset.last_depreciated_period,
             asset.disposal_date.isoformat() if asset.disposal_date else None,
             asset.disposal_journal_entry_id, asset.updated_at, asset.id),
        )

    def get(self, asset_id: str) -> FixedAsset | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM fixed_assets WHERE id=?", (asset_id,))
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> FixedAsset | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM fixed_assets WHERE operation_id=?", (operation_id,)
        )
        return _to_entity(row) if row else None

    def list_capitalized(self) -> list[FixedAsset]:
        rows = self._query(f"SELECT {_COLUMNS} FROM fixed_assets WHERE status='CAPITALIZED'")
        return [_to_entity(row) for row in rows]

    def list_all(self) -> list[FixedAsset]:
        rows = self._query(f"SELECT {_COLUMNS} FROM fixed_assets ORDER BY name")
        return [_to_entity(row) for row in rows]
