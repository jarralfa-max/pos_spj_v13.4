"""Read-only repository for VENTAS UI queries (ticket reprint, sale lookup, QR).

Extracted from modulos/ventas.py (Fase A): the PyQt UI ran these SELECTs inline.
PyQt-free and headless-testable. Reads only — no writes, no transactions.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class SalesReadRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        try:
            if getattr(self._connection, "row_factory", None) is None:
                self._connection.row_factory = sqlite3.Row
        except Exception:
            pass

    def get_qr_container(self, uuid_qr: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT uuid_qr, descripcion FROM trazabilidad_qr WHERE uuid_qr=? LIMIT 1",
            (uuid_qr,),
        ).fetchone()
        if row is None:
            return None
        return {"uuid_qr": row[0], "descripcion": row[1]}

    def get_sale_ticket_header(self, sale_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT folio, fecha, usuario, forma_pago, efectivo_recibido, cambio, total "
            "FROM ventas WHERE id=?",
            (sale_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "folio": row[0], "fecha": row[1], "usuario": row[2],
            "forma_pago": row[3], "efectivo_recibido": row[4],
            "cambio": row[5], "total": row[6],
        }

    def get_sale_items_with_product(self, sale_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT p.nombre, dv.cantidad, dv.precio_unitario, dv.subtotal, "
            "COALESCE(p.unidad,'pz') as unidad "
            "FROM detalles_venta dv JOIN productos p ON p.id=dv.producto_id "
            "WHERE dv.venta_id=?",
            (sale_id,),
        ).fetchall()
        return [
            {"nombre": r[0], "cantidad": float(r[1]), "precio_unitario": float(r[2]),
             "total": float(r[3] or 0), "unidad": r[4]}
            for r in rows
        ]

    def find_sale_by_folio_or_id(self, folio_or_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT id, folio, total, estado FROM ventas WHERE folio=? OR CAST(id AS TEXT)=?",
            (folio_or_id, folio_or_id),
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "folio": row[1], "total": row[2], "estado": row[3]}

    def get_sale_items_basic(self, sale_id: str) -> list[tuple]:
        """Returns (nombre, cantidad, precio_unitario, importe) tuples for the
        positional table render in the cancel-sale dialog."""
        rows = self._connection.execute(
            "SELECT nombre, cantidad, precio_unitario, (cantidad*precio_unitario) "
            "FROM detalles_venta WHERE venta_id=?",
            (sale_id,),
        ).fetchall()
        return [tuple(r) for r in rows]
