# infrastructure/persistence/sqlite_sales_repository.py — SPJ ERP v13.4
"""
SQLite implementation of the sales persistence repository.

This is the canonical infrastructure-layer replacement for repositories/sales_repository.py.
It inherits from BaseRepository and adds no business logic — only data access.

Migration status: parallel to repositories/sales_repository.py (legacy shim remains
for backward compatibility). AppContainer should eventually inject this class.
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from infrastructure.persistence.base import BaseRepository

logger = logging.getLogger("spj.infrastructure.sales_repository")


class SQLiteSalesRepository(BaseRepository):
    """
    SQLite data-access layer for the ventas / detalles_venta tables.

    Responsibilities:
      - Persist sale headers and line items (write)
      - Read sales by ID, folio, date, or branch (read)
      - Never apply business rules — those live in SalesService / domain
    """

    # ── Write ─────────────────────────────────────────────────────────────────

    def create_sale(
        self,
        branch_id: int,
        user: str,
        client_id: Optional[int],
        subtotal: float,
        discount: float,
        total: float,
        payment_method: str,
        amount_paid: float,
        operation_id: str,
        notes: str = "",
    ) -> Tuple[int, str]:
        """
        Insert a sale header row.

        Returns:
            (sale_id, folio) — folio is unique per sale
        """
        folio = self._unique_folio()
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sale_id = self._lastrowid("""
            INSERT INTO ventas (
                folio, sucursal_id, usuario, cliente_id,
                subtotal, descuento, total,
                forma_pago, efectivo_recibido,
                operation_id, observations, estado, fecha
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,'completada',?)
        """, (
            folio, branch_id, user, client_id,
            subtotal, discount, total,
            payment_method, amount_paid,
            operation_id, notes, fecha,
        ))
        logger.debug("sale created id=%d folio=%s", sale_id, folio)
        return sale_id, folio

    def save_sale_item(
        self,
        sale_id: int,
        product_id: int,
        qty: float,
        unit_price: float,
        subtotal: float,
        cost: float = 0.0,
        discount: float = 0.0,
    ) -> None:
        """Insert a single line item for a sale."""
        self._execute("""
            INSERT INTO detalles_venta (
                venta_id, producto_id, cantidad, precio_unitario,
                subtotal, costo_unitario_real, descuento
            ) VALUES (?,?,?,?,?,?,?)
        """, (sale_id, product_id, qty, unit_price, subtotal, cost, discount))

    def cancel_sale(self, sale_id: int, reason: str = "") -> None:
        """Mark a sale as cancelled."""
        self._execute(
            "UPDATE ventas SET estado='cancelada', observations=? WHERE id=?",
            (reason or "Cancelled", sale_id),
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_by_id(self, sale_id: int) -> Optional[Dict]:
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

    def get_items(self, sale_id: int) -> List[Dict]:
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
        branch_id: int,
        date_start: str,
        date_end: str,
    ) -> List[Dict]:
        rows = self._fetchall("""
            SELECT v.id, v.folio, v.usuario, v.total, v.subtotal,
                   v.descuento, v.forma_pago, v.estado, v.fecha,
                   COALESCE(c.nombre,'') || ' ' || COALESCE(c.apellido,'') AS cliente_nombre
            FROM ventas v
            LEFT JOIN clientes c ON c.id = v.cliente_id
            WHERE v.sucursal_id = ?
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
              AND v.estado != 'cancelada'
            ORDER BY v.fecha DESC
        """, (branch_id, date_start, date_end))
        return [dict(r) for r in rows]

    def get_today(self, branch_id: int, date: Optional[str] = None) -> List[Dict]:
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        return self.get_by_date_range(branch_id, date, date)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _unique_folio(self) -> str:
        base = datetime.now().strftime("%Y%m%d%H%M%S")
        for _ in range(5):
            folio = f"VNT-{base}-{uuid.uuid4().hex[:4].upper()}"
            exists = self._fetchone("SELECT 1 FROM ventas WHERE folio=? LIMIT 1", (folio,))
            if not exists:
                return folio
        return f"VNT-{base}-{uuid.uuid4().hex[:8].upper()}"
