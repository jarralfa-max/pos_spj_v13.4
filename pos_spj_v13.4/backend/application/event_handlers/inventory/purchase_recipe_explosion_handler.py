"""PurchaseRecipeExplosionHandler (Inventory context).

Migrated from the monolith's `_procesar_recetas`: when a purchased product has an
active recipe (BOM), buying it consumes its components (transformation-on-
purchase, e.g. buying marinated chicken consumes raw chicken + marinade). This
handler consumes ``PURCHASE_STOCK_ENTRY_REGISTERED`` and, per line whose product
has a recipe, deducts each component ``cantidad_insumo × quantity`` via a
``movimientos_inventario`` 'salida' (the trigger subtracts the stock).

Idempotent per (event, product): a replayed event does not double-deduct. Only
inventory movement rows are written; the recipe tables are read-only here.
"""

from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.inventory.purchase_recipe_explosion")


def _dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


class PurchaseRecipeExplosionHandler:
    event_name = "PURCHASE_STOCK_ENTRY_REGISTERED"

    def __init__(self, connection) -> None:
        self._conn = connection

    def handle(self, payload: dict) -> None:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            return
        lines = payload.get("lines") or []
        sucursal_id = str(payload.get("warehouse_id") or payload.get("branch_id") or "")
        usuario = str(payload.get("user_id") or "system")
        try:
            wrote = False
            for line in lines:
                wrote |= self._explode_line(line, event_id=event_id,
                                            sucursal_id=sucursal_id, usuario=usuario)
            if wrote:
                self._conn.commit()
        except Exception:
            rollback = getattr(self._conn, "rollback", None)
            if rollback is not None:
                rollback()
            raise

    def _explode_line(self, line: dict, *, event_id: str, sucursal_id: str,
                      usuario: str) -> bool:
        product_id = str(line.get("product_id") or "")
        qty = _dec(line.get("quantity"))
        if not product_id or qty <= 0:
            return False
        reference_id = f"{event_id}:{product_id}:recipe"
        # idempotency: a prior explosion of this (event, product) short-circuits.
        if self._conn.execute(
                "SELECT 1 FROM movimientos_inventario WHERE referencia_id=? LIMIT 1",
                (reference_id,)).fetchone():
            return False
        components = self._recipe_components(product_id)
        if not components:
            return False
        for comp in components:
            insumo_id = str(comp["insumo_id"])
            consumo = _dec(comp["cantidad_insumo"]) * qty
            if consumo <= 0:
                continue
            self._conn.execute(
                "INSERT INTO movimientos_inventario"
                " (id, producto_id, tipo, tipo_movimiento, cantidad, descripcion,"
                "  referencia, referencia_id, referencia_tipo, usuario, sucursal_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (new_uuid(), insumo_id, "salida", "RECETA_COMPRA", float(consumo),
                 "Receta de compra", product_id, reference_id, "RECETA_COMPRA",
                 usuario, sucursal_id))
        return True

    def _recipe_components(self, product_id: str) -> list[dict]:
        for sql in (
            "SELECT rc.producto_id AS insumo_id, COALESCE(rc.cantidad,0) AS cantidad_insumo"
            " FROM receta_componentes rc JOIN recetas r ON r.id=rc.receta_id"
            " WHERE (r.producto_base_id=? OR r.producto_id=?) AND (r.activo=1 OR r.activa=1)",
            "SELECT rc.component_product_id AS insumo_id, COALESCE(rc.cantidad,0) AS cantidad_insumo"
            " FROM product_recipe_components rc JOIN product_recipes r ON r.id=rc.recipe_id"
            " WHERE r.base_product_id=? AND r.is_active=1",
        ):
            params = (product_id, product_id) if "producto_base_id" in sql else (product_id,)
            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                continue
            if rows:
                cols = ["insumo_id", "cantidad_insumo"]
                return [dict(zip(cols, r)) for r in rows]
        return []
