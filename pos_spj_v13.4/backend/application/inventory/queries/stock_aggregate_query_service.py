"""InventoryStockAggregateQueryService — lecturas agregadas de stock (INV-27 / G1).

Provee los agregados que los reportes/BI/forecast legacy calculaban sobre
``productos.existencia`` (``SUM(existencia)``, conteos de stock bajo), ahora
derivados de la proyección canónica ``inventory_balances``:

    disponible = Σ quantity − Σ reserved_quantity   (status AVAILABLE)

El "stock bajo" compara el disponible de cada (producto, sucursal) contra el
``reorder_point`` canónico de ``inventory_replenishment_rule`` (INV-18),
agregando por sucursal cuando hay reglas por almacén — el equivalente canónico de
``existencia <= stock_minimo``.

Read-only y **Decimal en todo**: las cantidades se guardan como texto decimal, así
que se agregan en Python con ``Decimal`` (nunca ``SUM()`` en SQL sobre TEXT, que
pasaría por float).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.inventory.enums import InventoryStatus
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
)

_AVAILABLE = InventoryStatus.AVAILABLE.value


@dataclass(frozen=True, slots=True)
class LowStockItemDTO:
    product_id: str
    branch_id: str
    available: Decimal
    reorder_point: Decimal
    min_quantity: Decimal


@dataclass(frozen=True, slots=True)
class LowStockProductDTO:
    product_id: str
    available: Decimal
    reorder_point: Decimal
    min_quantity: Decimal


class InventoryStockAggregateQueryService(InventoryRepositoryBase):
    # ── disponible por producto ───────────────────────────────────────────────
    def available_by_product(self, *, branch_id: str | None = None) -> dict[str, Decimal]:
        """Disponible total por ``product_id`` (todas las sucursales o una)."""
        sql = ("SELECT product_id, quantity, reserved_quantity FROM inventory_balances"
               " WHERE inventory_status=?")
        params: tuple = (_AVAILABLE,)
        if branch_id is not None:
            sql += " AND branch_id=?"
            params += (branch_id,)
        out: dict[str, Decimal] = {}
        for r in self._query(sql, params):
            pid = r["product_id"]
            out[pid] = out.get(pid, Decimal("0")) + (
                to_decimal(r["quantity"]) - to_decimal(r["reserved_quantity"]))
        return out

    def total_available(self, *, product_id: str,
                        branch_id: str | None = None) -> Decimal:
        """Disponible de un producto (total o en una sucursal)."""
        sql = ("SELECT quantity, reserved_quantity FROM inventory_balances"
               " WHERE inventory_status=? AND product_id=?")
        params: tuple = (_AVAILABLE, product_id)
        if branch_id is not None:
            sql += " AND branch_id=?"
            params += (branch_id,)
        total = Decimal("0")
        for r in self._query(sql, params):
            total += to_decimal(r["quantity"]) - to_decimal(r["reserved_quantity"])
        return total

    # ── stock bajo ────────────────────────────────────────────────────────────
    def _available_by_product_branch(
            self, branch_id: str | None) -> dict[tuple[str, str], Decimal]:
        sql = ("SELECT product_id, branch_id, quantity, reserved_quantity"
               " FROM inventory_balances WHERE inventory_status=?")
        params: tuple = (_AVAILABLE,)
        if branch_id is not None:
            sql += " AND branch_id=?"
            params += (branch_id,)
        out: dict[tuple[str, str], Decimal] = {}
        for r in self._query(sql, params):
            key = (r["product_id"], r["branch_id"])
            out[key] = out.get(key, Decimal("0")) + (
                to_decimal(r["quantity"]) - to_decimal(r["reserved_quantity"]))
        return out

    def low_stock_items(self, *, branch_id: str | None = None) -> list[LowStockItemDTO]:
        """Items cuyo disponible (por sucursal) es ≤ su ``reorder_point`` canónico.

        Suma ``reorder_point``/``min_quantity`` por (producto, sucursal) cuando hay
        reglas por almacén, para comparar contra el disponible a nivel sucursal.
        """
        rule_sql = ("SELECT product_id, branch_id, reorder_point, min_quantity"
                    " FROM inventory_replenishment_rule WHERE active=1")
        params: tuple = ()
        if branch_id is not None:
            rule_sql += " AND branch_id=?"
            params += (branch_id,)
        reorder: dict[tuple[str, str], Decimal] = {}
        minq: dict[tuple[str, str], Decimal] = {}
        for r in self._query(rule_sql, params):
            key = (r["product_id"], r["branch_id"])
            reorder[key] = reorder.get(key, Decimal("0")) + to_decimal(r["reorder_point"])
            minq[key] = minq.get(key, Decimal("0")) + to_decimal(r["min_quantity"])

        available = self._available_by_product_branch(branch_id)
        items: list[LowStockItemDTO] = []
        for key, threshold in reorder.items():
            avail = available.get(key, Decimal("0"))
            if avail <= threshold:
                items.append(LowStockItemDTO(
                    product_id=key[0], branch_id=key[1], available=avail,
                    reorder_point=threshold, min_quantity=minq.get(key, Decimal("0"))))
        items.sort(key=lambda it: (it.product_id, it.branch_id))
        return items

    def low_stock_count(self, *, branch_id: str | None = None) -> int:
        return len(self.low_stock_items(branch_id=branch_id))

    # ── stock bajo a nivel producto (regla global, equiv. legacy stock_minimo) ─
    def low_stock_products(
            self, *, positive_threshold_only: bool = False) -> list[LowStockProductDTO]:
        """Productos cuyo disponible **total** (entre sucursales) es ≤ su umbral
        de reposición global (regla `branch_id=''`, respaldada desde el
        `stock_minimo` legacy por la migración 168). Equivalente canónico de
        ``existencia <= stock_minimo``.

        ``positive_threshold_only`` filtra a umbrales > 0 (equivalente al filtro
        legacy ``stock_minimo > 0`` que usa el motor de alertas).
        """
        rules = self._query(
            "SELECT product_id, reorder_point, min_quantity"
            " FROM inventory_replenishment_rule"
            " WHERE active=1 AND branch_id='' AND warehouse_id=''")
        available = self.available_by_product()
        out: list[LowStockProductDTO] = []
        for r in rules:
            reorder = to_decimal(r["reorder_point"])
            if positive_threshold_only and reorder <= 0:
                continue
            avail = available.get(r["product_id"], Decimal("0"))
            if avail <= reorder:
                out.append(LowStockProductDTO(
                    product_id=r["product_id"], available=avail,
                    reorder_point=reorder, min_quantity=to_decimal(r["min_quantity"])))
        out.sort(key=lambda it: it.product_id)
        return out

    def low_stock_products_count(self, *, positive_threshold_only: bool = False) -> int:
        return len(self.low_stock_products(positive_threshold_only=positive_threshold_only))

    # ── umbral global por producto (equiv. legacy stock_minimo, lectura puntual) ─
    def reorder_points_by_product(self) -> dict[str, Decimal]:
        """``reorder_point`` global (regla ``branch_id=''``/``warehouse_id=''``) por
        producto — equivalente canónico de ``productos.stock_minimo``."""
        sql = ("SELECT product_id, reorder_point FROM inventory_replenishment_rule"
               " WHERE active=1 AND branch_id='' AND warehouse_id=''")
        return {r["product_id"]: to_decimal(r["reorder_point"]) for r in self._query(sql)}

    def reorder_point_for_product(self, product_id: str) -> Decimal:
        """``reorder_point`` global de un solo producto (lectura puntual, sin
        cargar la tabla completa)."""
        row = self._query_one(
            "SELECT reorder_point FROM inventory_replenishment_rule"
            " WHERE active=1 AND branch_id='' AND warehouse_id='' AND product_id=?",
            (product_id,))
        return to_decimal(row["reorder_point"]) if row else Decimal("0")
