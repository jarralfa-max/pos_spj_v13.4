# infrastructure/persistence/sqlite_sales_repository.py — SPJ ERP v13.4
"""SQLite implementation of the sales persistence repository (UUID-only)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.shared.ids import new_uuid
from infrastructure.persistence.base import BaseRepository

logger = logging.getLogger("spj.infrastructure.sales_repository")


class SQLiteSalesRepository(BaseRepository):
    """SQLite data-access layer for ventas / detalles_venta tables.

    Identity contract: all IDs (sale_id, product_id, branch_id, client_id)
    are UUIDv7 TEXT strings. No integer IDs are accepted or returned.
    """

    # ── Write ─────────────────────────────────────────────────────────────────

    def create_sale(
        self,
        branch_id: str,
        user: str,
        client_id: Optional[str],
        subtotal: float,
        discount: float,
        total: float,
        payment_method: str,
        amount_paid: float,
        operation_id: str,
        notes: str = "",
    ) -> Tuple[str, str]:
        """Insert a sale header row.

        Returns:
            (sale_id, folio) — sale_id is a new UUIDv7; folio is human-readable.
        """
        sale_id = new_uuid()
        folio = self._unique_folio(sale_id)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._execute("""
            INSERT INTO ventas (
                id, folio, sucursal_id, usuario, cliente_id,
                subtotal, descuento, total,
                forma_pago, efectivo_recibido,
                operation_id, observations, estado, fecha
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'completada',?)
        """, (
            sale_id, folio, branch_id, user, client_id,
            subtotal, discount, total,
            payment_method, amount_paid,
            operation_id, notes, fecha,
        ))
        logger.debug("sale created id=%s folio=%s", sale_id, folio)
        return sale_id, folio

    def save_sale_item(
        self,
        sale_id: str,
        product_id: str,
        qty: float,
        unit_price: float,
        subtotal: float,
        cost: float = 0.0,
        discount: float = 0.0,
    ) -> None:
        """Insert a single line item for a sale."""
        item_id = new_uuid()
        self._execute("""
            INSERT INTO detalles_venta (
                id, venta_id, producto_id, cantidad, precio_unitario,
                subtotal, costo_unitario_real, descuento
            ) VALUES (?,?,?,?,?,?,?,?)
        """, (item_id, sale_id, product_id, qty, unit_price, subtotal, cost, discount))

    def cancel_sale(self, sale_id: str, reason: str = "") -> None:
        """Mark a sale as cancelled."""
        self._execute(
            "UPDATE ventas SET estado='cancelada', observations=? WHERE id=?",
            (reason or "Cancelled", sale_id),
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_by_id(self, sale_id: str) -> Optional[Dict]:
        row = self._fetchone("SELECT * FROM ventas WHERE id=?", (sale_id,))
        return dict(row) if row else None

    def get_by_folio(self, folio: str) -> Optional[Dict]:
        row = self._fetchone("SELECT * FROM ventas WHERE folio=?", (folio,))
        return dict(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> Optional[Dict]:
        row = self._fetchone(
            "SELECT id, folio, total FROM ventas WHERE operation_id=?",
            (operation_id,),
        )
        return dict(row) if row else None

    def get_items(self, sale_id: str) -> List[Dict]:
        rows = self._fetchall("""
            SELECT dv.id, dv.producto_id, p.nombre AS producto_nombre,
                   dv.cantidad, dv.precio_unitario, dv.subtotal,
                   dv.costo_unitario_real, dv.descuento
            FROM detalles_venta dv
            JOIN productos p ON p.id = dv.producto_id
            WHERE dv.venta_id = ?
        """, (sale_id,))
        return [dict(r) for r in rows]

    def get_by_date_range(
        self,
        branch_id: str,
        date_start: str,
        date_end: str,
    ) -> List[Dict]:
        rows = self._fetchall("""
            SELECT v.id, v.folio, v.usuario, v.total, v.subtotal,
                   v.descuento, v.forma_pago, v.estado, v.fecha,
                   COALESCE(c.nombre,'') AS cliente_nombre
            FROM ventas v
            LEFT JOIN clientes c ON c.id = v.cliente_id
            WHERE v.sucursal_id = ?
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
              AND v.estado != 'cancelada'
            ORDER BY v.fecha DESC
        """, (branch_id, date_start, date_end))
        return [dict(r) for r in rows]

    def get_today(self, branch_id: str, date: Optional[str] = None) -> List[Dict]:
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        return self.get_by_date_range(branch_id, date, date)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _unique_folio(self, sale_id: str) -> str:
        """Generate a human-readable unique folio incorporating the sale UUID."""
        base = datetime.now().strftime("%Y%m%d%H%M%S")
        # Use last 8 chars of UUID (random suffix) for collision safety
        suffix = sale_id.replace("-", "")[-8:].upper()
        return f"VNT-{base}-{suffix}"
