"""SQLite-backed waste repository for the canonical waste route."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.application.queries.base_query_service import KpiMetric, SearchResult, TableRow


class WasteRepository:
    """Owns persistence details for waste reads and writes."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def operation_exists(self, operation_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM mermas WHERE operation_id = ? LIMIT 1",
            (operation_id,),
        ).fetchone()
        return row is not None

    def get_product_for_waste(self, product_id: int | str) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT id, nombre, COALESCE(precio_compra,0), COALESCE(unidad,'kg'), COALESCE(existencia,0)
            FROM productos
            WHERE id = ? AND COALESCE(activo,1) = 1
            """,
            (product_id,),
        ).fetchone()
        return self._product_dict(row) if row else None

    def search_products(self, query: str, *, limit: int = 30) -> list[SearchResult]:
        like = f"%{query.strip()}%"
        rows = self._connection.execute(
            """
            SELECT id, nombre, COALESCE(precio_compra,0), COALESCE(unidad,'kg'), COALESCE(existencia,0)
            FROM productos
            WHERE COALESCE(activo,1) = 1 AND (? = '%%' OR nombre LIKE ?)
            ORDER BY nombre
            LIMIT ?
            """,
            (like, like, limit),
        ).fetchall()
        results: list[SearchResult] = []
        for row in rows:
            product = self._product_dict(row)
            results.append(SearchResult(
                id=str(product["id"]),
                label=str(product["name"]),
                subtitle=f"Stock: {product['stock']:.2f} {product['unit']} | Costo: ${product['unit_cost']:.2f}",
                metadata=product,
            ))
        return results

    def register_waste(self, entry: dict[str, Any]) -> str:
        cursor = self._connection.execute(
            """
            INSERT INTO mermas
            (producto_id, sucursal_id, cantidad, unidad, motivo, costo_unitario, valor_perdida,
             notas, usuario, operation_id, created_at, fecha)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["product_id"],
                entry["branch_id"],
                entry["quantity"],
                entry["unit"],
                entry["reason"],
                entry["unit_cost"],
                entry["loss_value"],
                entry["notes"],
                entry["user_name"],
                entry["operation_id"],
                datetime.now().isoformat(),
                entry["date"],
            ),
        )
        return str(cursor.lastrowid or entry["operation_id"])

    def decrease_inventory_for_waste(self, product_id: int | str, quantity: float) -> None:
        self._connection.execute(
            "UPDATE productos SET existencia = MAX(0, COALESCE(existencia,0) - ?) WHERE id = ?",
            (quantity, product_id),
        )

    def save_changes(self) -> None:
        if hasattr(self._connection, "commit"):
            self._connection.commit()

    def list_waste_records(self, *, branch_id: str | int, period: str = "Hoy", search: str = "", limit: int = 500) -> list[TableRow]:
        where_period = {
            "Hoy": "AND COALESCE(m.fecha, substr(m.created_at,1,10)) >= date('now')",
            "Última semana": "AND COALESCE(m.fecha, substr(m.created_at,1,10)) >= date('now','-7 days')",
            "Último mes": "AND COALESCE(m.fecha, substr(m.created_at,1,10)) >= date('now','-30 days')",
        }.get(period, "")
        search_clause = ""
        params: list[Any] = [branch_id]
        if search.strip():
            search_clause = "AND (p.nombre LIKE ? OR m.motivo LIKE ? OR m.usuario LIKE ?)"
            like = f"%{search.strip()}%"
            params.extend([like, like, like])
        params.append(limit)
        rows = self._connection.execute(
            f"""
            SELECT m.id, COALESCE(m.fecha, substr(m.created_at,1,10)) as fecha,
                   p.nombre, m.cantidad, m.unidad,
                   COALESCE(m.costo_unitario,0), COALESCE(m.valor_perdida,0),
                   m.motivo, m.usuario, COALESCE(m.notas,'')
            FROM mermas m
            JOIN productos p ON p.id = m.producto_id
            WHERE m.sucursal_id = ? {where_period} {search_clause}
            ORDER BY COALESCE(m.fecha, m.created_at) DESC, m.id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [self._row_to_table(row) for row in rows]

    def get_daily_summary(self, *, branch_id: str | int) -> KpiMetric:
        row = self._connection.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(COALESCE(valor_perdida,0)),0)
            FROM mermas
            WHERE sucursal_id = ? AND COALESCE(fecha, substr(created_at,1,10)) = date('now')
            """,
            (branch_id,),
        ).fetchone()
        records = int(row[0]) if row else 0
        loss_value = round(float(row[1] or 0), 2) if row else 0.0
        return KpiMetric("daily_waste", "Merma de hoy", {"records": records, "loss_value": loss_value})

    def _product_dict(self, row) -> dict[str, Any]:
        return {
            "id": row[0],
            "name": row[1],
            "unit_cost": float(row[2] or 0),
            "unit": str(row[3] or "kg"),
            "stock": float(row[4] or 0),
        }

    def _row_to_table(self, row) -> TableRow:
        return TableRow(str(row[0]), {
            "date": str(row[1] or "")[:10],
            "product_name": str(row[2] or ""),
            "quantity": float(row[3] or 0),
            "unit": str(row[4] or "kg"),
            "unit_cost": float(row[5] or 0),
            "loss_value": round(float(row[6] or 0), 2),
            "reason": str(row[7] or ""),
            "user_name": str(row[8] or ""),
            "notes": str(row[9] or ""),
        })
