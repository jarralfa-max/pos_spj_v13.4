"""UnitRepository — persistence for units, conversions and catch-weight config (PROD-5).

Decimal stays a string in the DB (no REAL); the repository maps Decimal ↔ str and
None ↔ NULL. It never commits — the caller owns the transaction boundary
(consistent with the inventory UoW contract). Parametrized queries only.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.products.entities.product_unit_conversion import (
    ProductUnitConversion,
)
from backend.domain.products.entities.unit_of_measure import UnitOfMeasure
from backend.domain.products.unit_enums import PriceBasis, UnitDimension
from backend.domain.products.value_objects.catch_weight_configuration import (
    CatchWeightConfiguration,
)


def _d(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


class UnitRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── units of measure ──────────────────────────────────────────────────
    def save_unit(self, unit: UnitOfMeasure) -> None:
        self._conn.execute(
            """INSERT INTO units_of_measure (id, code, name, dimension, active)
               VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 code=excluded.code, name=excluded.name,
                 dimension=excluded.dimension, active=excluded.active""",
            (unit.id, unit.code, unit.name, unit.dimension.value, int(unit.active)))

    def get_unit(self, unit_id: str) -> UnitOfMeasure | None:
        row = self._conn.execute(
            "SELECT * FROM units_of_measure WHERE id=?", (unit_id,)).fetchone()
        return self._row_to_unit(row) if row else None

    def list_units(self, *, dimension: UnitDimension | None = None) -> list[UnitOfMeasure]:
        if dimension is not None:
            rows = self._conn.execute(
                "SELECT * FROM units_of_measure WHERE dimension=? ORDER BY code",
                (dimension.value,)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM units_of_measure ORDER BY code").fetchall()
        return [self._row_to_unit(r) for r in rows]

    @staticmethod
    def _row_to_unit(row) -> UnitOfMeasure:
        return UnitOfMeasure(id=row["id"], code=row["code"], name=row["name"],
                             dimension=UnitDimension(row["dimension"]),
                             active=bool(row["active"]))

    # ── conversions ───────────────────────────────────────────────────────
    def save_conversion(self, conv: ProductUnitConversion) -> None:
        self._conn.execute(
            """INSERT INTO product_unit_conversions
               (id, product_id, from_unit_id, to_unit_id, factor, rounding_scale,
                effective_from, effective_to, active)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 factor=excluded.factor, rounding_scale=excluded.rounding_scale,
                 effective_from=excluded.effective_from,
                 effective_to=excluded.effective_to, active=excluded.active""",
            (conv.id, conv.product_id, conv.from_unit_id, conv.to_unit_id,
             str(conv.factor), int(conv.rounding_scale), conv.effective_from,
             conv.effective_to, int(conv.active)))

    def list_conversions(self, *, product_id: str | None = None) -> list[ProductUnitConversion]:
        """Global conversions plus any specific to ``product_id``."""
        if product_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM product_unit_conversions "
                "WHERE active=1 AND (product_id IS NULL OR product_id=?)",
                (product_id,)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM product_unit_conversions "
                "WHERE active=1 AND product_id IS NULL").fetchall()
        return [self._row_to_conv(r) for r in rows]

    @staticmethod
    def _row_to_conv(row) -> ProductUnitConversion:
        return ProductUnitConversion(
            id=row["id"], product_id=row["product_id"],
            from_unit_id=row["from_unit_id"], to_unit_id=row["to_unit_id"],
            factor=Decimal(row["factor"]), rounding_scale=int(row["rounding_scale"]),
            effective_from=row["effective_from"], effective_to=row["effective_to"],
            active=bool(row["active"]))

    # ── catch-weight configuration ────────────────────────────────────────
    def save_catch_weight(self, product_id: str, cfg: CatchWeightConfiguration) -> None:
        self._conn.execute(
            """INSERT INTO product_catch_weight_config
               (product_id, enabled, nominal_unit_id, weight_unit_id,
                minimum_weight, maximum_weight, average_weight, tolerance_pct,
                price_basis, label_required, scale_barcode_enabled, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
               ON CONFLICT(product_id) DO UPDATE SET
                 enabled=excluded.enabled, nominal_unit_id=excluded.nominal_unit_id,
                 weight_unit_id=excluded.weight_unit_id,
                 minimum_weight=excluded.minimum_weight,
                 maximum_weight=excluded.maximum_weight,
                 average_weight=excluded.average_weight,
                 tolerance_pct=excluded.tolerance_pct, price_basis=excluded.price_basis,
                 label_required=excluded.label_required,
                 scale_barcode_enabled=excluded.scale_barcode_enabled,
                 updated_at=datetime('now')""",
            (product_id, int(cfg.enabled), cfg.nominal_unit_id, cfg.weight_unit_id,
             None if cfg.minimum_weight is None else str(cfg.minimum_weight),
             None if cfg.maximum_weight is None else str(cfg.maximum_weight),
             None if cfg.average_weight is None else str(cfg.average_weight),
             str(cfg.tolerance_pct), cfg.price_basis.value,
             int(cfg.label_required), int(cfg.scale_barcode_enabled)))

    def get_catch_weight(self, product_id: str) -> CatchWeightConfiguration | None:
        row = self._conn.execute(
            "SELECT * FROM product_catch_weight_config WHERE product_id=?",
            (product_id,)).fetchone()
        if row is None:
            return None
        return CatchWeightConfiguration(
            enabled=bool(row["enabled"]),
            nominal_unit_id=row["nominal_unit_id"] or "",
            weight_unit_id=row["weight_unit_id"] or "",
            minimum_weight=_d(row["minimum_weight"]) or Decimal("0"),
            maximum_weight=_d(row["maximum_weight"]) or Decimal("0"),
            average_weight=_d(row["average_weight"]),
            tolerance_pct=_d(row["tolerance_pct"]) or Decimal("0"),
            price_basis=PriceBasis(row["price_basis"]),
            label_required=bool(row["label_required"]),
            scale_barcode_enabled=bool(row["scale_barcode_enabled"]))
