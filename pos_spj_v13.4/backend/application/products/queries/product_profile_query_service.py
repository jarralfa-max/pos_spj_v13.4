"""ProductProfileQueryService (PROD-22) — vida útil, calidad y logística de UN producto.

Read side del diálogo «Calidad, vida útil y logística» (§18-20). Los perfiles los
define Productos y los ejecutan Calidad/Inventario; los casos de uso existían
(PROD-8) sin pantalla que los capturara ni los mostrara. Los decimales se
devuelven como texto (nunca float) para que el formulario los muestre tal cual.
"""

from __future__ import annotations


def _row(cursor_row, cursor) -> dict | None:
    if cursor_row is None:
        return None
    return {d[0]: cursor_row[i] for i, d in enumerate(cursor.description)}


class ProductProfileQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _one(self, sql: str, product_id: str) -> dict | None:
        cursor = self._conn.execute(sql, (product_id,))
        return _row(cursor.fetchone(), cursor)

    def shelf_life(self, product_id: str) -> dict | None:
        """El perfil vigente (el más reciente)."""
        return self._one(
            "SELECT shelf_life_days, minimum_remaining_for_receipt, minimum_remaining_for_sale, "
            "storage_condition, opened_shelf_life_days, frozen_shelf_life_days, "
            "thawed_shelf_life_days FROM product_shelf_life_profiles WHERE product_id=? "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1", product_id)

    def quality(self, product_id: str) -> dict | None:
        return self._one(
            "SELECT inspection_required, temperature_required, weight_check_required, "
            "organoleptic_check_required, quarantine_required, fat_pct_min, fat_pct_max, "
            "moisture_pct_min, moisture_pct_max, color_requirement, odor_requirement, "
            "packaging_requirement, documentation_requirement "
            "FROM product_quality_profiles WHERE product_id=?", product_id)

    def logistics(self, product_id: str) -> dict | None:
        return self._one(
            "SELECT gross_weight, net_weight, weight_unit, dimensions, storage_temp_min, "
            "storage_temp_max, transport_temp_min, transport_temp_max, fragile, perishable, "
            "frozen, chilled, stackable, requires_cold_chain "
            "FROM product_logistics_profiles WHERE product_id=?", product_id)

    def catch_weight(self, product_id: str) -> dict | None:
        """Peso variable (§12); pesos y tolerancia como texto Decimal."""
        return self._one(
            "SELECT enabled, nominal_unit_id, weight_unit_id, minimum_weight, maximum_weight, "
            "average_weight, tolerance_pct, price_basis, label_required, scale_barcode_enabled "
            "FROM product_catch_weight_config WHERE product_id=?", product_id)
