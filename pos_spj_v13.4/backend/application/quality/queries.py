"""Lo que Calidad tiene por inspeccionar en una sucursal.

Lectura de presentación: el producto por su nombre, el lote por su código y lo
retenido por Inventario en cuarentena. No decide nada; decidir es
`DecideOutputInspectionUseCase`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PendingInspection:
    inspection_id: str
    product_name: str
    lot_code: str
    held_quantity: Decimal
    requested_at: str
    source_module: str


class PendingInspectionsQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_pending(self, branch_id: str, *, limit: int = 200) -> list[PendingInspection]:
        filas = self._conn.execute(
            "SELECT i.id, p.name, l.lot_code,"
            " (SELECT COALESCE(SUM(CAST(b.quantity AS REAL)), 0) FROM inventory_balances b"
            "   WHERE b.lot_id = i.lot_id AND b.product_id = i.product_id"
            "     AND b.inventory_status = 'QUARANTINED'),"
            " i.requested_at, i.source_module"
            " FROM quality_inspections i"
            " LEFT JOIN products p ON p.id = i.product_id"
            " LEFT JOIN inventory_lots l ON l.id = i.lot_id"
            " WHERE i.branch_id = ? AND i.status = 'PENDING'"
            " ORDER BY i.requested_at, i.id LIMIT ?", (branch_id, max(1, int(limit)))).fetchall()
        return [PendingInspection(
            inspection_id=str(f[0]), product_name=str(f[1] or ""), lot_code=str(f[2] or ""),
            held_quantity=Decimal(str(f[3] or 0)), requested_at=str(f[4] or ""),
            source_module=str(f[5] or "")) for f in filas]
