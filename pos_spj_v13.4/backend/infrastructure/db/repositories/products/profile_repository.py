"""ProfileRepository — persistence for shelf-life / quality / logistics profiles (PROD-8).

Decimal ↔ str, TemperatureRange ↔ three columns, None ↔ NULL. Never commits (the
caller owns the transaction). Parametrized queries only.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.products.entities.product_logistics_profile import (
    ProductLogisticsProfile,
)
from backend.domain.products.entities.product_quality_profile import (
    ProductQualityProfile,
)
from backend.domain.products.entities.product_shelf_life_profile import (
    ProductShelfLifeProfile,
)
from backend.domain.products.value_objects.temperature_range import TemperatureRange


def _d(v: str | None) -> Decimal | None:
    return None if v is None else Decimal(v)


def _s(v) -> str | None:
    return None if v is None else str(v)


class ProfileRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── shelf life ────────────────────────────────────────────────────────
    def save_shelf_life(self, p: ProductShelfLifeProfile) -> None:
        self._conn.execute(
            """INSERT INTO product_shelf_life_profiles
               (id, product_id, shelf_life_days, minimum_remaining_for_receipt,
                minimum_remaining_for_sale, storage_condition, opened_shelf_life_days,
                frozen_shelf_life_days, thawed_shelf_life_days, effective_from, effective_to)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 shelf_life_days=excluded.shelf_life_days,
                 minimum_remaining_for_receipt=excluded.minimum_remaining_for_receipt,
                 minimum_remaining_for_sale=excluded.minimum_remaining_for_sale,
                 storage_condition=excluded.storage_condition""",
            (p.id, p.product_id, p.shelf_life_days, p.minimum_remaining_for_receipt,
             p.minimum_remaining_for_sale, p.storage_condition, p.opened_shelf_life_days,
             p.frozen_shelf_life_days, p.thawed_shelf_life_days,
             p.effective_from, p.effective_to))

    def get_shelf_life(self, product_id: str) -> ProductShelfLifeProfile | None:
        row = self._conn.execute(
            "SELECT * FROM product_shelf_life_profiles WHERE product_id=? "
            "ORDER BY created_at DESC LIMIT 1", (product_id,)).fetchone()
        if row is None:
            return None
        return ProductShelfLifeProfile(
            id=row["id"], product_id=row["product_id"],
            shelf_life_days=row["shelf_life_days"],
            minimum_remaining_for_receipt=row["minimum_remaining_for_receipt"],
            minimum_remaining_for_sale=row["minimum_remaining_for_sale"],
            storage_condition=row["storage_condition"],
            opened_shelf_life_days=row["opened_shelf_life_days"],
            frozen_shelf_life_days=row["frozen_shelf_life_days"],
            thawed_shelf_life_days=row["thawed_shelf_life_days"],
            effective_from=row["effective_from"], effective_to=row["effective_to"])

    def has_shelf_life(self, product_id: str) -> bool:
        return self.get_shelf_life(product_id) is not None

    # ── quality ───────────────────────────────────────────────────────────
    def save_quality(self, q: ProductQualityProfile) -> None:
        self._conn.execute(
            """INSERT INTO product_quality_profiles
               (product_id, inspection_required, temperature_required,
                weight_check_required, organoleptic_check_required,
                microbiological_test_required, fat_pct_min, fat_pct_max,
                moisture_pct_min, moisture_pct_max, color_requirement,
                odor_requirement, packaging_requirement, documentation_requirement,
                quarantine_required, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
               ON CONFLICT(product_id) DO UPDATE SET
                 inspection_required=excluded.inspection_required,
                 quarantine_required=excluded.quarantine_required,
                 fat_pct_min=excluded.fat_pct_min, fat_pct_max=excluded.fat_pct_max,
                 updated_at=datetime('now')""",
            (q.product_id, int(q.inspection_required), int(q.temperature_required),
             int(q.weight_check_required), int(q.organoleptic_check_required),
             int(q.microbiological_test_required), _s(q.fat_pct_min), _s(q.fat_pct_max),
             _s(q.moisture_pct_min), _s(q.moisture_pct_max), q.color_requirement,
             q.odor_requirement, q.packaging_requirement, q.documentation_requirement,
             int(q.quarantine_required)))

    def get_quality(self, product_id: str) -> ProductQualityProfile | None:
        row = self._conn.execute(
            "SELECT * FROM product_quality_profiles WHERE product_id=?",
            (product_id,)).fetchone()
        if row is None:
            return None
        return ProductQualityProfile(
            product_id=row["product_id"],
            inspection_required=bool(row["inspection_required"]),
            temperature_required=bool(row["temperature_required"]),
            weight_check_required=bool(row["weight_check_required"]),
            organoleptic_check_required=bool(row["organoleptic_check_required"]),
            microbiological_test_required=bool(row["microbiological_test_required"]),
            fat_pct_min=_d(row["fat_pct_min"]), fat_pct_max=_d(row["fat_pct_max"]),
            moisture_pct_min=_d(row["moisture_pct_min"]),
            moisture_pct_max=_d(row["moisture_pct_max"]),
            color_requirement=row["color_requirement"],
            odor_requirement=row["odor_requirement"],
            packaging_requirement=row["packaging_requirement"],
            documentation_requirement=row["documentation_requirement"],
            quarantine_required=bool(row["quarantine_required"]))

    # ── logistics ─────────────────────────────────────────────────────────
    def save_logistics(self, lg: ProductLogisticsProfile) -> None:
        st = lg.storage_temperature
        tr = lg.transport_temperature
        self._conn.execute(
            """INSERT INTO product_logistics_profiles
               (product_id, gross_weight, net_weight, weight_unit, dimensions,
                storage_temp_min, storage_temp_max, storage_temp_unit,
                transport_temp_min, transport_temp_max, transport_temp_unit,
                fragile, perishable, frozen, chilled, stackable, shelf_life_days,
                open_package_shelf_life_days, requires_cold_chain, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
               ON CONFLICT(product_id) DO UPDATE SET
                 gross_weight=excluded.gross_weight, net_weight=excluded.net_weight,
                 requires_cold_chain=excluded.requires_cold_chain,
                 frozen=excluded.frozen, chilled=excluded.chilled,
                 updated_at=datetime('now')""",
            (lg.product_id, _s(lg.gross_weight), _s(lg.net_weight), lg.weight_unit,
             lg.dimensions,
             _s(st.minimum) if st else None, _s(st.maximum) if st else None,
             st.unit if st else None,
             _s(tr.minimum) if tr else None, _s(tr.maximum) if tr else None,
             tr.unit if tr else None,
             int(lg.fragile), int(lg.perishable), int(lg.frozen), int(lg.chilled),
             int(lg.stackable), lg.shelf_life_days, lg.open_package_shelf_life_days,
             int(lg.requires_cold_chain)))

    def get_logistics(self, product_id: str) -> ProductLogisticsProfile | None:
        row = self._conn.execute(
            "SELECT * FROM product_logistics_profiles WHERE product_id=?",
            (product_id,)).fetchone()
        if row is None:
            return None
        st = (TemperatureRange(_d(row["storage_temp_min"]), _d(row["storage_temp_max"]),
                               row["storage_temp_unit"] or "C")
              if row["storage_temp_min"] is not None else None)
        tr = (TemperatureRange(_d(row["transport_temp_min"]), _d(row["transport_temp_max"]),
                               row["transport_temp_unit"] or "C")
              if row["transport_temp_min"] is not None else None)
        return ProductLogisticsProfile(
            product_id=row["product_id"], gross_weight=_d(row["gross_weight"]),
            net_weight=_d(row["net_weight"]), weight_unit=row["weight_unit"],
            dimensions=row["dimensions"], storage_temperature=st, transport_temperature=tr,
            fragile=bool(row["fragile"]), perishable=bool(row["perishable"]),
            frozen=bool(row["frozen"]), chilled=bool(row["chilled"]),
            stackable=bool(row["stackable"]), shelf_life_days=row["shelf_life_days"],
            open_package_shelf_life_days=row["open_package_shelf_life_days"],
            requires_cold_chain=bool(row["requires_cold_chain"]))
