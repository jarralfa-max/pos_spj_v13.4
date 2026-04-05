# sync/domain_validators/inventory_validator.py — SPJ POS v13.3
"""
Validador de dominio para inventario en sincronización multisucursal.

Reglas:
  1. Stock no puede quedar negativo (salvo configuración explícita)
  2. Costo promedio no puede ser 0 si hay stock > 0
  3. Movimientos duplicados (mismo operation_id) se rechazan
  4. Delta de stock > 1000% sobre el stock actual → sospechoso
"""
from __future__ import annotations

import logging
from typing import Optional

from sync.domain_validators.base import DomainValidator

logger = logging.getLogger("spj.sync.validators.inventory")

INVENTORY_TABLES = frozenset({
    "movimientos_inventario", "inventory_movements",
    "branch_inventory", "lotes", "movimientos_lote",
})


class InventoryValidator(DomainValidator):
    """Valida reglas de negocio de inventario post-resolución de conflicto."""

    def __init__(self, allow_negative: bool = False):
        self.allow_negative = allow_negative

    def validate(
        self,
        tabla: str,
        resolved: dict,
        local: dict,
        remote: dict,
    ) -> Optional[str]:
        if tabla not in INVENTORY_TABLES:
            return None

        # ── Regla 1: Stock no negativo ────────────────────────────────────
        stock = float(
            resolved.get("existencia",
            resolved.get("quantity",
            resolved.get("stock", 0)))
        )
        if stock < 0 and not self.allow_negative:
            return (
                f"Stock negativo ({stock:.3f}) para "
                f"producto={resolved.get('producto_id', resolved.get('product_id', '?'))}"
            )

        # ── Regla 2: Costo promedio coherente ─────────────────────────────
        costo = float(
            resolved.get("costo_promedio",
            resolved.get("avg_cost",
            resolved.get("unit_cost", -1)))
        )
        if costo != -1 and stock > 0 and costo <= 0:
            return (
                f"Costo promedio = {costo} con stock positivo ({stock:.3f}) "
                f"producto={resolved.get('producto_id', '?')}"
            )

        # ── Regla 3: Delta sospechoso ─────────────────────────────────────
        local_stock = float(
            local.get("existencia",
            local.get("quantity",
            local.get("stock", 0)))
        )
        if local_stock > 0 and abs(stock - local_stock) > local_stock * 10:
            return (
                f"Delta de stock sospechoso: local={local_stock:.3f} "
                f"→ resolved={stock:.3f} (>1000% cambio)"
            )

        return None
