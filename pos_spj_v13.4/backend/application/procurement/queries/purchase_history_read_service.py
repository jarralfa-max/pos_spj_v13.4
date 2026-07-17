"""Documental purchase-history read service (migrated from the monolith's
"Historial de Compras" tab). Reads the canonical goods_receipts first and falls
back to the legacy recepciones for records not yet migrated. No business logic.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class PurchaseHistoryReadService:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            cur = self._conn.execute(sql, params)
        except sqlite3.OperationalError:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def canonical_receipts(self, *, branch_id: str | None = None,
                           limit: int = 100) -> list[dict]:
        where, params = "", []
        if branch_id:
            where = " WHERE branch_id=?"
            params.append(branch_id)
        return self._rows(
            "SELECT document_number, supplier_id, status, direct_purchase_id,"
            " purchase_order_id, created_at FROM goods_receipts"
            f"{where} ORDER BY created_at DESC LIMIT ?", (*params, int(limit)))

    def legacy_receptions(self, *, branch_id: str | None = None,
                          limit: int = 100) -> list[dict]:
        """Legacy documental receptions still readable until their tables migrate."""
        where, params = " WHERE r.tipo='COMPRA'", []
        if branch_id:
            where += " AND r.sucursal_id=?"
            params.append(branch_id)
        return self._rows(
            "SELECT r.folio, r.created_at, COALESCE(p.nombre,'—') AS supplier,"
            " r.condicion_pago, r.monto_total, r.monto_pagado, r.estado"
            " FROM recepciones r LEFT JOIN proveedores p ON p.id=r.proveedor_id"
            f"{where} ORDER BY r.created_at DESC LIMIT ?", (*params, int(limit)))
