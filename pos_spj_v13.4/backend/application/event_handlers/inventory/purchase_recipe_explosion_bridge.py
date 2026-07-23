"""CanonicalPurchaseRecipeExplosionHandler — corte INV-27.

Reemplaza al PurchaseRecipeExplosionHandler legacy: cuando un producto comprado
tiene receta (transformación-en-compra, p.ej. comprar pollo marinado consume
pollo crudo + marinada), consume sus componentes. El legacy escribía
``movimientos_inventario`` 'salida'; este postea UN movimiento ADJUSTMENT_OUT
canónico por evento con una línea por componente (cantidad_insumo × quantity),
idempotente por operation_id. Permite negativo (igual que el trigger legacy no
bloqueaba la transformación).

La lectura de la receta es idéntica al legacy (receta_componentes / product_recipe
_components). Solo cambia la mutación: al ledger canónico, no a tablas legacy.
"""

from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal

from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType

logger = logging.getLogger("spj.inventory.purchase_recipe_bridge")


def _dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


class CanonicalPurchaseRecipeExplosionHandler:
    event_name = "PURCHASE_STOCK_ENTRY_REGISTERED"

    def __init__(self, connection,
                 use_case: PostInventoryMovementUseCase | None = None) -> None:
        self._conn = connection
        self._uc = use_case or PostInventoryMovementUseCase()

    def handle(self, payload: dict) -> None:
        event_id = str(payload.get("event_id") or "").strip()
        lines = payload.get("lines") or []
        branch = str(payload.get("warehouse_id") or payload.get("branch_id") or "")
        user = str(payload.get("user_id") or "system")
        if not event_id or not branch or not lines:
            return
        for line in lines:
            self._explode_line(line, event_id=event_id, branch=branch, user=user)

    def _explode_line(self, line: dict, *, event_id: str, branch: str, user: str) -> None:
        product_id = str(line.get("product_id") or "")
        qty = _dec(line.get("quantity"))
        if not product_id or qty <= 0:
            return
        components = self._recipe_components(product_id)
        if not components:
            return
        movement_lines = []
        for comp in components:
            insumo_id = str(comp["insumo_id"])
            consumo = _dec(comp["cantidad_insumo"]) * qty
            if consumo <= 0 or not insumo_id:
                continue
            movement_lines.append(InventoryMovementLine.create(
                product_id=insumo_id, quantity=consumo, from_location_id=branch,
                from_status=InventoryStatus.AVAILABLE, reason_code="RECETA_COMPRA"))
        if not movement_lines:
            return
        movement = InventoryMovement.create(
            movement_type=MovementType.ADJUSTMENT_OUT, branch_id=branch,
            warehouse_id=branch, source_module="procurement",
            source_document_type="RECETA_COMPRA", source_document_id=product_id,
            operation_id=f"{event_id}:{product_id}:recipe",
            created_by_user_id=user, lines=movement_lines)
        # negative_allowed: la transformación en compra no se bloquea por faltante
        # (igual que el trigger legacy). El caso de uso commitea.
        result = self._uc.execute(self._conn, movement, actor_user_id=user,
                                  negative_allowed=True)
        if not result.success and result.error_code != "PERMISSION_DENIED":
            raise RuntimeError(result.message or "Fallo explosión de receta en compra.")

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
