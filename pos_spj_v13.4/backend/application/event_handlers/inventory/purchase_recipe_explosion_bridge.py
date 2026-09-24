"""CanonicalPurchaseRecipeExplosionHandler — corte INV-27.

Reemplaza al PurchaseRecipeExplosionHandler legacy: cuando un producto comprado
tiene receta (transformación-en-compra, p.ej. comprar pollo marinado consume
pollo crudo + marinada), consume sus componentes. El legacy escribía
``movimientos_inventario`` 'salida'; este postea UN movimiento ADJUSTMENT_OUT
canónico por evento con una línea por componente (cantidad_insumo × quantity),
idempotente por operation_id. Permite negativo (igual que el trigger legacy no
bloqueaba la transformación).

FASE 2 (2026-09-17) — LA RECETA SALE DEL CATÁLOGO CANÓNICO DE PRODUCTOS
-----------------------------------------------------------------------
Este puente leía `receta_componentes`/`recetas` y, si no, `product_recipe_
components`/`product_recipes`: los DOS catálogos legacy. Medido: **nada en el
código de producción escribe en ninguno de los dos**, y el que escribe el
módulo de Productos —`recipes`/`recipe_versions`/`recipe_components`— no lo
leía. Una receta creada hoy en Productos nunca se aplicaba al comprar. Es lo
que el §13 del prompt prohíbe: más de un catálogo de recetas.

Ahora usa la MISMA pareja que Ventas (`sale_items_bridge._explode_bom`):
`RecipeRepository.active_version_for_product` + `RecipeExplosionService`. Una
sola regla de explosión para vender y para comprar, y una sola fuente.

Por qué no se pierde nada: la migración 152 ya copió ambos catálogos legacy al
canónico CONSERVANDO los ids, y convirtió `producto_base_id` en
`recipes.product_id` —justo la llave de `active_version_for_product`—. En la
base real los tres catálogos están vacíos (medido en sólo lectura).

Dos cambios de comportamiento, ambos deliberados:
* **Sólo la versión ACTIVA explota.** El legacy aceptaba cualquier receta con
  `activo=1`; el canónico distingue borrador, en revisión y activa, y consumir
  según una fórmula que nadie aprobó es lo que Ventas ya se niega a hacer.
* **Se incluye la merma de la receta** (`gross_quantity`), igual que Ventas. En
  las recetas migradas no cambia nada: el legacy no tenía merma y la 152 la dejó
  en cero.
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
        """Componentes POR UNIDAD de la versión activa de la receta canónica.

        Sin receta activa no hay nada que consumir: comprar un producto sin
        receta sólo da entrada al inventario (lo hace otro manejador).
        """
        from backend.domain.products.services.recipe_explosion_service import (
            RecipeExplosionService,
        )
        from backend.infrastructure.db.repositories.products.recipe_repository import (
            RecipeRepository,
        )
        try:
            version = RecipeRepository(self._conn).active_version_for_product(product_id)
        except sqlite3.OperationalError:
            # Base sin el esquema de Productos: no hay recetas que aplicar.
            return []
        if version is None:
            return []
        return [{"insumo_id": str(c.component_product_id), "cantidad_insumo": c.quantity}
                for c in RecipeExplosionService().explode(version, Decimal("1"))]
