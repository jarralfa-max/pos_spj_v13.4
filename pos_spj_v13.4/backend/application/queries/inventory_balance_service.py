"""
InventoryBalanceQueryService — canonical single source of truth for product stock.

Both Producción Cárnica and Inventario modules MUST read through this service.
It reads from inventory_stock (the table all writers update) and enriches
the result with reservation data when available.

Usage:
    svc = InventoryBalanceQueryService(db_connection)
    balance = svc.get_product_balance(producto_id=3, sucursal_id=1)
    print(balance["stock_disponible"])   # Decimal

Only get_product_balance()/get_product_balance_float() remain: they are the
sole methods with a reachable caller (core/services/delivery_service.py,
modulos/delivery.py, core/services/production_query_service.py), and both
are already cutover-aware (read inventory_balances when the INV-27 flag is
ON). list_branch_balances() and get_reconciliation_report() had zero
production callers — the live enterprise inventory UI
(frontend/desktop/modules/inventory/) reads exclusively through the
canonical query services in backend/application/inventory/queries/ and
backend/application/inventory/cutover/ — and were removed.
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

logger = logging.getLogger("spj.inventory.balance")

_ZERO = Decimal("0")
_QUANT = Decimal("0.0001")


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(_QUANT, rounding=ROUND_HALF_UP)
    except Exception:
        return _ZERO


def _tbl_exists(conn, name: str) -> bool:
    try:
        r = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return r is not None
    except Exception:
        return False


class InventoryBalanceQueryService:
    """
    Single canonical read path for product inventory balances.

    Primary source: inventory_stock (branch-aware, updated by ALL writers).
    Fallback:       productos.existencia  (global, only when inventory_stock missing).

    Returns Decimal values to avoid float rounding drift.
    """

    def __init__(self, conn) -> None:
        self._db = conn
        self._has_inv_actual = _tbl_exists(conn, "inventory_stock")
        self._has_reservas = _tbl_exists(conn, "stock_reservas")

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_product_balance(
        self,
        producto_id: int,
        sucursal_id: int,
    ) -> dict[str, Any]:
        """
        Return a complete balance dict for a product+branch combination.

        Keys:
            producto_id      int
            sucursal_id      int
            unidad_base      str
            stock_fisico     Decimal  — physical stock in inventory_stock
            stock_reservado  Decimal  — committed to active reservas
            stock_comprometido Decimal — (currently = reservado; extend for pedidos)
            stock_transito   Decimal  — (reserved for future: transfers in transit)
            stock_disponible Decimal  — stock_fisico - stock_reservado
            fuente           str      — "inventory_stock" | "productos.existencia"
        """
        producto_id = str(producto_id)
        sucursal_id = str(sucursal_id)

        stock_fisico = _ZERO
        stock_reservado = _ZERO
        fuente = "unknown"
        canonical = False

        # INV-27 (reads follow writes): with the cutover flag ON the canonical
        # projection owns stock; read physical + reserved from inventory_balances.
        from backend.application.inventory.cutover import is_cutover_enabled
        if is_cutover_enabled(self._db) and _tbl_exists(self._db, "inventory_balances"):
            canonical = True
            fuente = "inventory_balances"
            for r in self._db.execute(
                "SELECT quantity, reserved_quantity FROM inventory_balances"
                " WHERE product_id=? AND branch_id=? AND inventory_status='AVAILABLE'",
                (producto_id, sucursal_id),
            ).fetchall():
                stock_fisico += _dec(r[0])
                stock_reservado += _dec(r[1])
        elif self._has_inv_actual:
            row = self._db.execute(
                "SELECT COALESCE(quantity, 0) FROM inventory_stock "
                "WHERE product_id=? AND branch_id=?",
                (producto_id, sucursal_id),
            ).fetchone()
            if row is not None:
                stock_fisico = _dec(row[0])
                fuente = "inventory_stock"
            else:
                # No branch row yet — fall back to productos.existencia (global)
                row2 = self._db.execute(
                    "SELECT COALESCE(existencia, 0) FROM productos WHERE id=?",
                    (producto_id,),
                ).fetchone()
                stock_fisico = _dec(row2[0] if row2 else 0)
                fuente = "productos.existencia"
        else:
            row2 = self._db.execute(
                "SELECT COALESCE(existencia, 0) FROM productos WHERE id=?",
                (producto_id,),
            ).fetchone()
            stock_fisico = _dec(row2[0] if row2 else 0)
            fuente = "productos.existencia"

        # Unit
        unit_row = self._db.execute(
            "SELECT COALESCE(unidad, 'kg') FROM productos WHERE id=?", (producto_id,)
        ).fetchone()
        unidad_base = str(unit_row[0] if unit_row else "kg")

        # Reservations — legacy source only when not already read from canonical.
        if not canonical and self._has_reservas:
            try:
                res_row = self._db.execute(
                    """
                    SELECT COALESCE(SUM(d.cantidad), 0)
                    FROM stock_reserva_detalles d
                    JOIN stock_reservas r ON r.id = d.reserva_id
                    WHERE r.estado = 'activa'
                      AND r.branch_id = ?
                      AND d.producto_id = ?
                    """,
                    (sucursal_id, producto_id),
                ).fetchone()
                stock_reservado = _dec(res_row[0] if res_row else 0)
            except Exception as exc:
                logger.debug("get_product_balance: reservas query failed: %s", exc)

        stock_disponible = max(_ZERO, stock_fisico - stock_reservado)

        logger.debug(
            "get_product_balance producto_id=%s sucursal_id=%s "
            "fisico=%s reservado=%s disponible=%s fuente=%s",
            producto_id, sucursal_id, stock_fisico, stock_reservado, stock_disponible, fuente,
        )

        return {
            "producto_id":        producto_id,
            "sucursal_id":        sucursal_id,
            "unidad_base":        unidad_base,
            "stock_fisico":       stock_fisico,
            "stock_reservado":    stock_reservado,
            "stock_comprometido": stock_reservado,
            "stock_transito":     _ZERO,
            "stock_disponible":   stock_disponible,
            "fuente":             fuente,
        }

    def get_product_balance_float(self, producto_id: int, sucursal_id: int) -> float:
        """Convenience method returning stock_disponible as float (for legacy callers)."""
        b = self.get_product_balance(producto_id, sucursal_id)
        return float(b["stock_disponible"])

    @classmethod
    def from_connection(cls, conn) -> "InventoryBalanceQueryService":
        return cls(conn)
