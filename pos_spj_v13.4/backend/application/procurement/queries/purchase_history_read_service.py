"""Documental purchase-history read service (migrated from the monolith's
"Historial de Compras" tab). Reads the canonical goods_receipts first and falls
back to the legacy recepciones for records not yet migrated. No business logic.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.application.procurement.dto.enterprise_dtos import PurchaseHistoryRowDTO


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
                           limit: int = 100) -> list[PurchaseHistoryRowDTO]:
        where, params = "", []
        if branch_id:
            where = " WHERE branch_id=?"
            params.append(branch_id)
        rows = self._rows(
            "SELECT document_number, goods_receipts.supplier_id, status, direct_purchase_id,"
            " purchase_order_id, goods_receipts.created_at,"
            " COALESCE(p.nombre, '—') AS supplier_name FROM goods_receipts"
            " LEFT JOIN proveedores p ON p.id = goods_receipts.supplier_id"
            f"{where} ORDER BY goods_receipts.created_at DESC LIMIT ?", (*params, int(limit)))
        return [PurchaseHistoryRowDTO(
            document_number=r["document_number"], supplier_id=r["supplier_id"],
            supplier_name=r["supplier_name"], status=r["status"],
            created_at=r["created_at"], direct_purchase_id=r["direct_purchase_id"],
            purchase_order_id=r["purchase_order_id"]) for r in rows]

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
