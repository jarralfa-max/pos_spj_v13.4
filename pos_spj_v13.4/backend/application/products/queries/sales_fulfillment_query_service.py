"""Con qué se surte la venta de un producto — contrato de lectura de Productos
para Ventas e Inventario (decisión del usuario, 2026-09-24).

Un producto COMPUESTO se vende pero no se almacena: al venderlo se consumen sus
componentes. Productos lo define de dos maneras y ambas cuentan:

- una receta ACTIVA de tipo «Explosión de venta» (`SALES_EXPLOSION`);
- un combo/paquete (bundle) VIRTUAL con versión ACTIVA (sin los componentes
  opcionales); un kit con existencia propia se vende de su stock.

Un componente que a su vez es compuesto se expande (anidado). Un ciclo o un
producto definido de las dos maneras es un dato maestro inválido: se falla claro,
no se adivina ni se vende "el compuesto como si tuviera existencia".

Un producto que no es compuesto se surte a sí mismo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.products.recipe_enums import RecipeType

_MAX_DEPTH = 8


class CompositeDefinitionError(ValueError):
    """La composición de venta no se puede resolver (ciclo o definición doble)."""


@dataclass(frozen=True)
class FulfillmentLine:
    product_id: str
    quantity: Decimal


class SalesFulfillmentQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── definición de un nivel ──────────────────────────────────────────
    def _sales_recipe_version(self, product_id: str):
        from backend.infrastructure.db.repositories.products.recipe_repository import (
            RecipeRepository,
        )
        fila = self._conn.execute(
            "SELECT rv.id FROM recipe_versions rv JOIN recipes r ON r.id = rv.recipe_id"
            " WHERE r.product_id=? AND r.recipe_type=? AND r.active=1 AND rv.status='ACTIVE'"
            " ORDER BY rv.version_number DESC LIMIT 1",
            (product_id, RecipeType.SALES_EXPLOSION.value)).fetchone()
        return RecipeRepository(self._conn).get_version(fila[0]) if fila else None

    def _bundle_version(self, product_id: str):
        """Versión activa de un combo que se descompone AL VENDER. Un kit con
        existencia propia (`STOCKED_KIT`) se arma antes y se vende de su stock."""
        from backend.domain.products.bundle_enums import VIRTUAL_TYPES
        from backend.infrastructure.db.repositories.products.bundle_repository import (
            BundleRepository,
        )
        fila = self._conn.execute(
            "SELECT v.id FROM bundle_versions v JOIN product_bundles b ON b.id = v.bundle_id"
            " WHERE b.product_id=? AND b.active=1 AND v.status='ACTIVE'"
            f" AND b.bundle_type IN ({','.join('?' * len(VIRTUAL_TYPES))})"
            " ORDER BY v.version_number DESC LIMIT 1",
            (product_id, *sorted(t.value for t in VIRTUAL_TYPES))).fetchone()
        return BundleRepository(self._conn).get_version(fila[0]) if fila else None

    def _one_level(self, product_id: str, quantity: Decimal) -> list[FulfillmentLine] | None:
        import sqlite3

        from backend.domain.products.services.bundle_explosion_service import (
            BundleExplosionService,
        )
        from backend.domain.products.services.recipe_explosion_service import (
            RecipeExplosionService,
        )
        try:
            receta = self._sales_recipe_version(product_id)
            combo = self._bundle_version(product_id)
        except sqlite3.OperationalError as exc:
            # Sin el esquema de recetas/combos de Productos no puede haber
            # compuestos definidos; cualquier otro error sí se propaga.
            if "no such table" in str(exc):
                return None
            raise
        if receta is not None and combo is not None:
            raise CompositeDefinitionError(
                f"El producto {product_id} tiene receta de venta Y combo activos; "
                "deja sólo uno en Productos.")
        if receta is not None:
            return [FulfillmentLine(c.component_product_id, Decimal(str(c.quantity)))
                    for c in RecipeExplosionService().explode(receta, quantity)]
        if combo is not None:
            return [FulfillmentLine(c.component_product_id, Decimal(str(c.quantity)))
                    for c in BundleExplosionService().explode(combo, quantity)]
        return None

    # ── contrato ─────────────────────────────────────────────────────────
    def is_composite(self, product_id: str) -> bool:
        return self._one_level(product_id, Decimal("1")) is not None

    def explode(self, product_id: str, quantity) -> dict[str, Decimal]:
        """{producto que se consume: cantidad} para vender ``quantity`` de
        ``product_id``, con los compuestos anidados expandidos."""
        cantidad = Decimal(str(quantity))
        total: dict[str, Decimal] = {}
        self._expand(product_id, cantidad, total, camino=())
        return total

    def _expand(self, product_id, cantidad, total, *, camino) -> None:
        if product_id in camino:
            raise CompositeDefinitionError(
                "Ciclo en la composición de venta: " + " → ".join((*camino, product_id)))
        if len(camino) >= _MAX_DEPTH:
            raise CompositeDefinitionError("Composición de venta demasiado profunda")
        nivel = self._one_level(product_id, cantidad) if cantidad > 0 else None
        if nivel is None:
            total[product_id] = total.get(product_id, Decimal("0")) + cantidad
            return
        for linea in nivel:
            self._expand(linea.product_id, linea.quantity, total, camino=(*camino, product_id))
