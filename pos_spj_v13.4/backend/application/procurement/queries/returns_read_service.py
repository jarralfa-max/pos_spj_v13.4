"""Lecturas del puesto de devoluciones y reversos (auditoría Compras C26).

Recepciones completadas que se pueden reversar o devolver, lo que cada línea
recibida todavía admite devolver, y las devoluciones con su estado. La regla de
«cuánto se puede devolver» es la MISMA del caso de uso (``_return_basis``).
"""

from __future__ import annotations

from typing import Any


class PurchaseReturnsReadService:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _has_returns(self) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='purchase_returns'"
        ).fetchone() is not None

    def completed_receipts(self, *, branch_id: str | None = None, limit: int = 100) -> list[dict]:
        where = " AND g.branch_id=?" if branch_id else ""
        params: tuple = ((branch_id, limit) if branch_id else (limit,))
        has_master = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='supplier_master'"
        ).fetchone() is not None
        supplier_name = ("COALESCE((SELECT legal_name FROM supplier_master sm"
                         " WHERE sm.id = g.supplier_id), g.supplier_id)" if has_master
                         else "g.supplier_id")
        return self._query(
            "SELECT g.id, g.document_number, g.supplier_id, g.branch_id, g.warehouse_id,"
            " g.purchase_order_id, g.direct_purchase_id, g.created_at,"
            " COALESCE(po.document_number, dp.document_number, '') AS source_number,"
            f" {supplier_name} AS supplier_name"
            " FROM goods_receipts g"
            " LEFT JOIN purchase_orders po ON po.id = g.purchase_order_id"
            " LEFT JOIN direct_purchases dp ON dp.id = g.direct_purchase_id"
            f" WHERE g.status='COMPLETED'{where} ORDER BY g.created_at DESC LIMIT ?", params)

    def returnable_lines(self, goods_receipt_id: str) -> list[dict]:
        from backend.application.procurement.use_cases.purchase_return_use_cases import (
            _return_basis,
        )
        from backend.infrastructure.db.repositories.procurement.unit_of_work import (
            ProcurementUnitOfWork,
        )
        with ProcurementUnitOfWork(self._conn) as uow:
            receipt = uow.receipts.get(goods_receipt_id)
            if receipt is None:
                return []
            basis = _return_basis(uow, receipt) if self._has_returns() else {}
        return [{"goods_receipt_line_id": line_id, "product_id": data["product_id"],
                 "available": format(data["available"].normalize(), "f")}
                for line_id, data in basis.items() if data["available"] > 0]

    def returns(self, *, branch_id: str | None = None, limit: int = 100) -> list[dict]:
        if not self._has_returns():
            return []
        where = " WHERE r.branch_id=?" if branch_id else ""
        params: tuple = ((branch_id, limit) if branch_id else (limit,))
        return self._query(
            "SELECT r.id, r.document_number, r.supplier_id, r.status, r.reason,"
            " r.goods_receipt_id, r.created_at, g.document_number AS receipt_number"
            " FROM purchase_returns r LEFT JOIN goods_receipts g ON g.id = r.goods_receipt_id"
            f"{where} ORDER BY r.created_at DESC LIMIT ?", params)
