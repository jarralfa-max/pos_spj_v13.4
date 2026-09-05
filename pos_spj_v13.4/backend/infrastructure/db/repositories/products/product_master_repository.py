"""ProductMasterRepository — canonical `products` master writes (PROD-19 paso 7b).

Born-clean: UUIDv7 id, no price/stock columns (guardrail
`test_product_master_does_not_own_pricing`). Parametrized SQL only; never commits
(the caller/use case owns the transaction).
"""

from __future__ import annotations

from typing import Any

_CAP_FLAGS = (
    "sellable", "purchasable", "inventory_managed", "producible", "internal_only",
    "recipe_allowed", "bundle_allowed", "lot_controlled", "expiration_controlled",
    "catch_weight_enabled", "quality_controlled", "traceability_required",
)


class ProductMasterRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def code_exists(self, code: str, *, exclude_id: str | None = None) -> bool:
        if exclude_id:
            row = self._conn.execute(
                "SELECT 1 FROM products WHERE code=? AND id<>? LIMIT 1",
                (code, exclude_id)).fetchone()
        else:
            row = self._conn.execute(
                "SELECT 1 FROM products WHERE code=? LIMIT 1", (code,)).fetchone()
        return row is not None

    def get(self, product_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        return dict(row) if row is not None else None

    def create(self, data: dict[str, Any]) -> None:
        flags = {f: 1 if data.get(f) else 0 for f in _CAP_FLAGS}
        self._conn.execute(
            f"""INSERT INTO products (
                    id, code, name, name_normalized, short_name, description,
                    product_type, lifecycle_status, internal_stage, category_id,
                    brand_id, parent_product_id, species_id,
                    base_unit_id, created_by, {', '.join(_CAP_FLAGS)})
                VALUES (:id, :code, :name, :name_normalized, :short_name, :description,
                    :product_type, :lifecycle_status, :internal_stage, :category_id,
                    :brand_id, :parent_product_id, :species_id,
                    :base_unit_id, :created_by, {', '.join(':' + f for f in _CAP_FLAGS)})""",
            {"brand_id": None, "parent_product_id": None, "internal_stage": "NONE",
             **data, **flags})

    def update_lifecycle(self, product_id: str, *, status: str,
                         activated_at: str | None = None,
                         discontinued_at: str | None = None) -> None:
        """Sólo cambia el estado de ciclo de vida (casos de uso de lifecycle)."""
        self._conn.execute(
            "UPDATE products SET lifecycle_status=:status, "
            "activated_at=COALESCE(:activated_at, activated_at), "
            "discontinued_at=COALESCE(:discontinued_at, discontinued_at), "
            "updated_at=datetime('now') WHERE id=:id",
            {"status": status, "activated_at": activated_at,
             "discontinued_at": discontinued_at, "id": product_id})

    def update(self, product_id: str, data: dict[str, Any]) -> None:
        flags = {f: 1 if data.get(f) else 0 for f in _CAP_FLAGS}
        self._conn.execute(
            f"""UPDATE products SET
                    code=:code, name=:name, name_normalized=:name_normalized,
                    short_name=:short_name, description=:description,
                    product_type=:product_type, lifecycle_status=:lifecycle_status,
                    internal_stage=:internal_stage,
                    category_id=:category_id, brand_id=:brand_id, species_id=:species_id,
                    base_unit_id=:base_unit_id, updated_at=datetime('now'),
                    {', '.join(f'{f}=:{f}' for f in _CAP_FLAGS)}
                WHERE id=:id""",
            {"brand_id": None, "internal_stage": "NONE", **data, **flags,
             "id": product_id})
