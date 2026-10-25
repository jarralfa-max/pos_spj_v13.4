"""FixedAsset repository — activos, categorías y corridas de depreciación (§17)."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.finance.entities.fixed_asset import FixedAsset, FixedAssetCategory
from backend.domain.finance.enums import DepreciationMethod, FixedAssetStatus
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import (
    FinanceRepositoryBase,
    iso,
    parse_date,
)
from backend.shared.ids import new_uuid


def _to_entity(row: dict) -> FixedAsset:
    currency = row["currency_code"]
    return FixedAsset(
        id=row["id"], name=row["name"], asset_code=row["asset_code"] or "",
        asset_category_id=row["asset_category_id"],
        acquisition_date=parse_date(row["acquisition_date"]),
        acquisition_cost=Money.from_string(row["acquisition_cost"], currency),
        residual_value=Money.from_string(row["residual_value"], currency),
        accumulated_depreciation=Money.from_string(row["accumulated_depreciation"], currency),
        useful_life_months=row["useful_life_months"],
        depreciation_method=DepreciationMethod(row["depreciation_method"]),
        status=FixedAssetStatus(row["status"]), status_reason=row["status_reason"],
        capitalization_date=parse_date(row["capitalization_date"]),
        asset_account_id=row["asset_account_id"],
        depreciation_expense_account_id=row["depreciation_expense_account_id"],
        accumulated_depreciation_account_id=row["accumulated_depreciation_account_id"],
        last_depreciated_period=row["last_depreciated_period"],
        disposal_date=parse_date(row["disposal_date"]),
        disposal_journal_entry_id=row["disposal_journal_entry_id"],
        supplier_id=row["supplier_id"], source_document_id=row["source_document_id"],
        project_id=row["project_id"],
        branch_id=row["branch_id"], cost_center_id=row["cost_center_id"],
        operation_id=row["operation_id"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _mutable(asset: FixedAsset) -> dict:
    return {
        "accumulated_depreciation": asset.accumulated_depreciation.to_string(),
        "status": asset.status.value, "status_reason": asset.status_reason,
        "acquisition_date": iso(asset.acquisition_date),
        "capitalization_date": iso(asset.capitalization_date),
        "asset_account_id": asset.asset_account_id,
        "depreciation_expense_account_id": asset.depreciation_expense_account_id,
        "accumulated_depreciation_account_id": asset.accumulated_depreciation_account_id,
        "last_depreciated_period": asset.last_depreciated_period,
        "disposal_date": iso(asset.disposal_date),
        "disposal_journal_entry_id": asset.disposal_journal_entry_id,
        "updated_at": asset.updated_at,
    }


def _category_to_entity(row: dict) -> FixedAssetCategory:
    return FixedAssetCategory(
        id=row["id"], code=row["code"], name=row["name"],
        asset_account_id=row["asset_account_id"],
        depreciation_expense_account_id=row["depreciation_expense_account_id"],
        accumulated_depreciation_account_id=row["accumulated_depreciation_account_id"],
        default_useful_life_months=row["default_useful_life_months"],
        active=bool(row["active"]), created_at=row["created_at"])


class FixedAssetRepository(FinanceRepositoryBase):
    def save(self, asset: FixedAsset) -> None:
        values = {
            "id": asset.id, "asset_code": asset.asset_code, "name": asset.name,
            "asset_category_id": asset.asset_category_id,
            "acquisition_cost": asset.acquisition_cost.to_string(),
            "residual_value": asset.residual_value.to_string(),
            "currency_code": asset.acquisition_cost.currency_code,
            "useful_life_months": asset.useful_life_months,
            "depreciation_method": asset.depreciation_method.value,
            "supplier_id": asset.supplier_id, "source_document_id": asset.source_document_id,
            "project_id": asset.project_id, "branch_id": asset.branch_id,
            "cost_center_id": asset.cost_center_id, "operation_id": asset.operation_id,
            "created_at": asset.created_at,
        }
        values.update(_mutable(asset))
        self._insert("fixed_assets", values)

    def update(self, asset: FixedAsset) -> None:
        self._update("fixed_assets", _mutable(asset), where="id=?", params=(asset.id,))

    def get(self, asset_id: str) -> FixedAsset | None:
        row = self._query_one("SELECT * FROM fixed_assets WHERE id=?", (asset_id,))
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> FixedAsset | None:
        row = self._query_one("SELECT * FROM fixed_assets WHERE operation_id=?", (operation_id,))
        return _to_entity(row) if row else None

    def list_capitalized(self) -> list[FixedAsset]:
        """Activos en servicio (ACTIVO) — los únicos que deprecian."""
        return [_to_entity(r) for r in
                self._query("SELECT * FROM fixed_assets WHERE status='ACTIVE'")]

    def list_all(self) -> list[FixedAsset]:
        return [_to_entity(r) for r in self._query("SELECT * FROM fixed_assets ORDER BY name")]

    # ── categorías ───────────────────────────────────────────────────────
    def save_category(self, category: FixedAssetCategory) -> None:
        self._insert("fixed_asset_categories", {
            "id": category.id, "code": category.code, "name": category.name,
            "asset_account_id": category.asset_account_id,
            "depreciation_expense_account_id": category.depreciation_expense_account_id,
            "accumulated_depreciation_account_id": category.accumulated_depreciation_account_id,
            "default_useful_life_months": category.default_useful_life_months,
            "active": int(category.active), "created_at": category.created_at,
        })

    def get_category(self, category_id: str) -> FixedAssetCategory | None:
        row = self._query_one("SELECT * FROM fixed_asset_categories WHERE id=?", (category_id,))
        return _category_to_entity(row) if row else None

    def get_category_by_code(self, code: str) -> FixedAssetCategory | None:
        row = self._query_one("SELECT * FROM fixed_asset_categories WHERE code=?", (code,))
        return _category_to_entity(row) if row else None

    def list_categories(self) -> list[FixedAssetCategory]:
        return [_category_to_entity(r) for r in self._query(
            "SELECT * FROM fixed_asset_categories WHERE active=1 ORDER BY code")]

    # ── corridas de depreciación (§17: la acumulada sólo cambia por corrida) ──
    def find_run_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one("SELECT * FROM depreciation_runs WHERE operation_id=?",
                               (operation_id,))

    def list_runs(self, period_code: str | None = None) -> list[dict]:
        if period_code is None:
            return self._query("SELECT * FROM depreciation_runs ORDER BY run_at DESC")
        return self._query("SELECT * FROM depreciation_runs WHERE period_code=?"
                           " ORDER BY run_at", (period_code,))

    def save_run(self, *, period_code: str, lines: list[tuple[str, Money, str]],
                 run_by: str | None, operation_id: str, currency_code: str) -> str:
        """``lines``: (activo, importe, asiento). Un activo se deprecia a lo más
        una vez por periodo (UNIQUE en las líneas); otra corrida del mismo
        periodo sólo incluye lo que faltaba (p. ej. un activo capitalizado después)."""
        from decimal import Decimal
        run_id = new_uuid()
        total = sum((amount.amount for _, amount, _ in lines), Decimal("0"))
        self._insert("depreciation_runs", {
            "id": run_id, "period_code": period_code, "asset_count": len(lines),
            "total_amount": format(Money(total, currency_code).amount, "f"),
            "currency_code": currency_code, "run_by": run_by, "operation_id": operation_id,
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        for asset_id, amount, entry_id in lines:
            self._insert("depreciation_run_lines", {
                "id": new_uuid(), "depreciation_run_id": run_id, "fixed_asset_id": asset_id,
                "period_code": period_code, "amount": amount.to_string(),
                "journal_entry_id": entry_id,
            })
        return run_id

    def run_lines(self, period_code: str) -> list[dict]:
        return self._query("SELECT * FROM depreciation_run_lines WHERE period_code=?",
                           (period_code,))
