"""
InventoryBalanceQueryService — canonical single source of truth for product stock.

Both Producción Cárnica and Inventario modules MUST read through this service.
It reads from inventory_stock (the table all writers update) and enriches
the result with reservation data when available.

Usage:
    svc = InventoryBalanceQueryService(db_connection)
    balance = svc.get_product_balance(producto_id=3, sucursal_id=1)
    print(balance["stock_disponible"])   # Decimal

    # Reconciliation report
    rows = svc.get_reconciliation_report(sucursal_id=1)
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


def _col_exists(conn, table: str, col: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r[1] == col for r in rows)
    except Exception:
        return False


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
        fuente = "unknown"

        if self._has_inv_actual:
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

        # Reservations
        stock_reservado = _ZERO
        if self._has_reservas:
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

    def list_branch_balances(self, sucursal_id: int) -> list[dict[str, Any]]:
        """
        Return balance for every active product at a given branch.
        Used by both Producción and Inventario UI tables.
        """
        sucursal_id = str(sucursal_id)
        out: list[dict[str, Any]] = []

        if self._has_inv_actual:
            rows = self._db.execute(
                """
                SELECT ia.product_id,
                       p.nombre,
                       '' AS categoria,
                       COALESCE(ia.quantity, 0)      AS stock_fisico,
                       COALESCE(p.stock_minimo, 0)   AS stock_minimo,
                       COALESCE(ia.costo_promedio, 0) AS costo_promedio,
                       COALESCE(p.unidad, 'kg')       AS unidad_base
                FROM inventory_stock ia
                JOIN productos p ON p.id = ia.product_id
                WHERE ia.branch_id = ?
                  AND COALESCE(p.activo, 1) = 1
                ORDER BY p.nombre
                """,
                (sucursal_id,),
            ).fetchall()
            for r in rows:
                pid = int(r[0])
                fisico = _dec(r[3])
                out.append({
                    "producto_id":    pid,
                    "nombre":         str(r[1] or ""),
                    "categoria":      str(r[2] or ""),
                    "stock_fisico":   fisico,
                    "stock_minimo":   _dec(r[4]),
                    "costo_promedio": _dec(r[5]),
                    "unidad_base":    str(r[6] or "kg"),
                    "stock_reservado":  _ZERO,
                    "stock_disponible": fisico,
                    "fuente":         "inventory_stock",
                })
        else:
            rows = self._db.execute(
                """
                SELECT id, nombre, COALESCE(categoria,''),
                       COALESCE(existencia,0), COALESCE(stock_minimo,0),
                       COALESCE(unidad,'kg')
                FROM productos
                WHERE COALESCE(activo,1) = 1
                ORDER BY nombre
                """,
            ).fetchall()
            for r in rows:
                fisico = _dec(r[3])
                out.append({
                    "producto_id":    int(r[0]),
                    "nombre":         str(r[1] or ""),
                    "categoria":      str(r[2] or ""),
                    "stock_fisico":   fisico,
                    "stock_minimo":   _dec(r[4]),
                    "costo_promedio": _ZERO,
                    "unidad_base":    str(r[5] or "kg"),
                    "stock_reservado":  _ZERO,
                    "stock_disponible": fisico,
                    "fuente":         "productos.existencia",
                })
        return out

    def get_reconciliation_report(self, sucursal_id: int) -> list[dict[str, Any]]:
        """
        Compare materialised stock in inventory_stock vs reconstructed from
        movimientos_inventario.  Returns rows where difference != 0.

        Columns: producto_id, nombre, unidad, saldo_materializado,
                 saldo_movimientos, diferencia
        """
        sucursal_id = str(sucursal_id)
        rows: list[dict[str, Any]] = []

        if not self._has_inv_actual:
            logger.warning("get_reconciliation_report: inventory_stock table missing")
            return rows

        has_movimientos = _tbl_exists(self._db, "movimientos_inventario")
        if not has_movimientos:
            logger.warning("get_reconciliation_report: movimientos_inventario table missing")
            return rows

        try:
            result = self._db.execute(
                """
                SELECT ia.product_id,
                       p.nombre,
                       COALESCE(p.unidad,'kg')       AS unidad,
                       COALESCE(ia.quantity, 0)       AS saldo_mat,
                       COALESCE(saldo.saldo_mov, 0)   AS saldo_mov
                FROM inventory_stock ia
                JOIN productos p ON p.id = ia.product_id
                LEFT JOIN (
                    SELECT producto_id,
                           SUM(CASE
                               WHEN tipo IN ('ENTRADA','PRODUCCION')      THEN cantidad
                               WHEN tipo IN ('SALIDA','MERMA','TRASPASO') THEN -cantidad
                               ELSE 0
                           END) AS saldo_mov
                    FROM movimientos_inventario
                    WHERE sucursal_id = ?
                    GROUP BY producto_id
                ) saldo ON saldo.producto_id = ia.product_id
                WHERE ia.branch_id = ?
                ORDER BY ABS(COALESCE(ia.quantity,0) - COALESCE(saldo.saldo_mov,0)) DESC
                """,
                (sucursal_id, sucursal_id),
            ).fetchall()

            for r in result:
                mat = _dec(r[3])
                mov = _dec(r[4])
                diff = mat - mov
                rows.append({
                    "producto_id":        int(r[0]),
                    "nombre":             str(r[1] or ""),
                    "unidad":             str(r[2] or ""),
                    "saldo_materializado": mat,
                    "saldo_movimientos":  mov,
                    "diferencia":         diff,
                })
        except Exception as exc:
            logger.error("get_reconciliation_report failed: %s", exc)
        return rows

    @classmethod
    def from_connection(cls, conn) -> "InventoryBalanceQueryService":
        return cls(conn)
