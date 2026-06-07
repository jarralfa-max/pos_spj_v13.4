"""SQLite-backed waste repository for the canonical waste route."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.application.queries.base_query_service import KpiMetric, SearchResult, TableRow


class WasteRepository:
    """Owns persistence details for waste reads and writes."""

    def __init__(self, connection) -> None:
        self._connection = connection
        self._table_exists_cache: dict[str, bool] = {}
        self._table_columns_cache: dict[str, set[str]] = {}

    def operation_exists(self, operation_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM mermas WHERE operation_id = ? LIMIT 1",
            (operation_id,),
        ).fetchone()
        return row is not None

    def get_product_for_waste(self, product_id: int | str, *, branch_id: str | int | None = None) -> dict[str, Any] | None:
        stock_expr, stock_params = self._branch_stock_expression(branch_id)
        cost_expr = self._product_cost_expression()
        row = self._connection.execute(
            f"""
            SELECT p.id, p.nombre, {cost_expr}, COALESCE(p.unidad,'kg'), {stock_expr}
            FROM productos p
            WHERE p.id = ? AND COALESCE(p.activo,1) = 1
            """,
            (*stock_params, product_id),
        ).fetchone()
        return self._product_dict(row) if row else None

    def search_products(self, query: str, *, limit: int = 30, branch_id: str | int | None = None) -> list[SearchResult]:
        like = f"%{query.strip()}%"
        stock_expr, stock_params = self._branch_stock_expression(branch_id)
        cost_expr = self._product_cost_expression()
        rows = self._connection.execute(
            f"""
            SELECT p.id, p.nombre, {cost_expr}, COALESCE(p.unidad,'kg'), {stock_expr}
            FROM productos p
            WHERE COALESCE(p.activo,1) = 1 AND (? = '%%' OR p.nombre LIKE ?)
            ORDER BY p.nombre
            LIMIT ?
            """,
            (*stock_params, like, like, limit),
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

    def decrease_inventory_for_waste(
        self,
        product_id: int | str,
        quantity: float,
        *,
        branch_id: str | int | None = None,
        unit_cost: float = 0.0,
        operation_id: str | None = None,
        reason: str = "",
        user_name: str = "",
    ) -> None:
        stock_before = self._stock_for_product(product_id, branch_id=branch_id)
        stock_after = max(0.0, stock_before - float(quantity))
        if branch_id is not None:
            self._decrease_branch_inventory(product_id, quantity, branch_id)
        self._connection.execute(
            "UPDATE productos SET existencia = MAX(0, COALESCE(existencia,0) - ?) WHERE id = ?",
            (quantity, product_id),
        )
        self._insert_inventory_movement_for_waste(
            product_id=product_id,
            quantity=quantity,
            branch_id=branch_id,
            unit_cost=unit_cost,
            operation_id=operation_id,
            reason=reason,
            user_name=user_name,
            stock_before=stock_before,
            stock_after=stock_after,
        )

    def save_changes(self) -> None:
        if hasattr(self._connection, "commit"):
            self._connection.commit()

    def rollback_changes(self) -> None:
        if hasattr(self._connection, "rollback"):
            self._connection.rollback()

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

    def _product_cost_expression(self) -> str:
        columns = self._table_columns("productos") if self._table_exists("productos") else set()
        candidates = [
            column for column in ("precio_compra", "costo", "precio_costo", "costo_unitario")
            if column in columns
        ]
        if not candidates:
            return "0"
        return "COALESCE(" + ", ".join(f"NULLIF(p.{column}, 0)" for column in candidates) + ", 0)"

    def _stock_for_product(self, product_id: int | str, *, branch_id: str | int | None = None) -> float:
        stock_expr, stock_params = self._branch_stock_expression(branch_id)
        row = self._connection.execute(
            f"SELECT {stock_expr} FROM productos p WHERE p.id = ?",
            (*stock_params, product_id),
        ).fetchone()
        return float(row[0] or 0) if row else 0.0

    def _branch_stock_expression(self, branch_id: str | int | None) -> tuple[str, list[Any]]:
        stock_sources = []
        params: list[Any] = []
        if branch_id is not None and self._table_exists("branch_inventory"):
            stock_sources.append(
                "(SELECT SUM(COALESCE(quantity,0)) "
                "FROM branch_inventory bi "
                "WHERE bi.product_id = p.id AND bi.branch_id = ?)"
            )
            params.append(branch_id)
        if branch_id is not None and self._table_exists("inventario_actual"):
            stock_sources.append(
                "(SELECT COALESCE(ia.cantidad,0) "
                "FROM inventario_actual ia "
                "WHERE ia.producto_id = p.id AND ia.sucursal_id = ? "
                "LIMIT 1)"
            )
            params.append(branch_id)
        stock_sources.append("COALESCE(p.existencia,0)")
        return f"COALESCE({', '.join(stock_sources)}, 0)", params

    def _decrease_branch_inventory(self, product_id: int | str, quantity: float, branch_id: str | int) -> None:
        if self._table_exists("inventario_actual"):
            updated = self._connection.execute(
                """
                UPDATE inventario_actual
                SET cantidad = MAX(0, COALESCE(cantidad,0) - ?),
                    ultima_actualizacion = datetime('now')
                WHERE producto_id = ? AND sucursal_id = ?
                """,
                (quantity, product_id, branch_id),
            ).rowcount
            if not updated:
                self._connection.execute(
                    """
                    INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
                    VALUES (?, ?, 0)
                    """,
                    (product_id, branch_id),
                )
        if self._table_exists("branch_inventory"):
            self._decrease_branch_inventory_rows(product_id, quantity, branch_id)

    def _decrease_branch_inventory_rows(self, product_id: int | str, quantity: float, branch_id: str | int) -> None:
        columns = self._table_columns("branch_inventory")
        has_batch = "batch_id" in columns
        has_updated_at = "updated_at" in columns
        order_by = "CASE WHEN batch_id IS NULL THEN 0 ELSE 1 END, rowid" if has_batch else "rowid"
        rows = self._connection.execute(
            f"""
            SELECT rowid, COALESCE(quantity,0)
            FROM branch_inventory
            WHERE product_id = ? AND branch_id = ?
            ORDER BY {order_by}
            """,
            (product_id, branch_id),
        ).fetchall()
        remaining = max(0.0, float(quantity))
        for rowid, current_qty in rows:
            if remaining <= 1e-9:
                break
            current = float(current_qty or 0)
            decrease = min(current, remaining)
            new_qty = max(0.0, current - decrease)
            set_updated_at = ", updated_at = datetime('now')" if has_updated_at else ""
            self._connection.execute(
                f"UPDATE branch_inventory SET quantity = ?{set_updated_at} WHERE rowid = ?",
                (new_qty, rowid),
            )
            remaining -= decrease
        if not rows:
            self._insert_empty_branch_inventory(product_id, branch_id, has_batch, has_updated_at)

    def _insert_empty_branch_inventory(
        self,
        product_id: int | str,
        branch_id: str | int,
        has_batch: bool,
        has_updated_at: bool,
    ) -> None:
        if has_batch and has_updated_at:
            self._connection.execute(
                """
                INSERT INTO branch_inventory (product_id, branch_id, quantity, batch_id, updated_at)
                VALUES (?, ?, 0, NULL, datetime('now'))
                """,
                (product_id, branch_id),
            )
        elif has_updated_at:
            self._connection.execute(
                """
                INSERT INTO branch_inventory (product_id, branch_id, quantity, updated_at)
                VALUES (?, ?, 0, datetime('now'))
                """,
                (product_id, branch_id),
            )
        elif has_batch:
            self._connection.execute(
                """
                INSERT INTO branch_inventory (product_id, branch_id, quantity, batch_id)
                VALUES (?, ?, 0, NULL)
                """,
                (product_id, branch_id),
            )
        else:
            self._connection.execute(
                """
                INSERT INTO branch_inventory (product_id, branch_id, quantity)
                VALUES (?, ?, 0)
                """,
                (product_id, branch_id),
            )

    def _insert_inventory_movement_for_waste(
        self,
        *,
        product_id: int | str,
        quantity: float,
        branch_id: str | int | None,
        unit_cost: float,
        operation_id: str | None,
        reason: str,
        user_name: str,
        stock_before: float,
        stock_after: float,
    ) -> None:
        if not self._table_exists("movimientos_inventario"):
            return
        import uuid as _uuid
        columns = self._table_columns("movimientos_inventario")
        values: dict[str, Any] = {
            "uuid": str(_uuid.uuid4()),
            "producto_id": product_id,
            "tipo": "MERMA",
            "tipo_movimiento": "waste",
            "tipo_movimiento_v2": "waste",
            "cantidad": float(quantity),
            "existencia_anterior": stock_before,
            "existencia_nueva": stock_after,
            "costo_unitario": float(unit_cost or 0),
            "costo_total": round(float(quantity) * float(unit_cost or 0), 2),
            "descripcion": reason or "Merma",
            "referencia": operation_id,
            "referencia_tipo": "WASTE",
            "nota": reason or "Merma",
            "operation_id": operation_id,
            "usuario": user_name or "",
            "sucursal_id": branch_id,
            "fecha": datetime.now().isoformat(),
        }
        insert_columns = [column for column in values if column in columns]
        if not insert_columns:
            return
        placeholders = ", ".join("?" for _ in insert_columns)
        self._connection.execute(
            f"INSERT INTO movimientos_inventario ({', '.join(insert_columns)}) VALUES ({placeholders})",
            tuple(values[column] for column in insert_columns),
        )

    def _table_exists(self, table_name: str) -> bool:
        if table_name not in self._table_exists_cache:
            row = self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
                (table_name,),
            ).fetchone()
            self._table_exists_cache[table_name] = row is not None
        return self._table_exists_cache[table_name]

    def _table_columns(self, table_name: str) -> set[str]:
        if table_name not in self._table_columns_cache:
            rows = self._connection.execute(f"PRAGMA table_info({table_name})").fetchall()
            self._table_columns_cache[table_name] = {str(row[1]) for row in rows}
        return self._table_columns_cache[table_name]

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
