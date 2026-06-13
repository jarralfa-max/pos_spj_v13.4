"""Read-only QueryService for product UI/API read models."""

from __future__ import annotations

import logging
from typing import Any

from backend.application.queries.base_query_service import BaseQueryService, KpiMetric, QueryFilters, SearchResult, TableRow
from backend.domain.services.product_type_policy import ProductTypePolicy


class SQLiteProductQueryDataSource:
    """Product read adapter used by desktop until a repository-backed API is wired."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        try:
            import sqlite3
            if getattr(self._connection, "row_factory", None) is None:
                self._connection.row_factory = sqlite3.Row
        except Exception:
            pass

    def search(self, scope: str, query: str, filters: QueryFilters | None = None) -> Sequence[SearchResult]:
        if scope != "products":
            return []
        like = f"%{query}%"
        rows = self._connection.execute(
            """
            SELECT id, nombre, codigo, categoria, unidad, precio, tipo_producto
            FROM productos
            WHERE COALESCE(activo,1)=1
              AND (? = '' OR nombre LIKE ? OR COALESCE(codigo,'') LIKE ? OR COALESCE(codigo_barras,'') LIKE ?)
            ORDER BY nombre ASC
            LIMIT 50
            """,
            (query, like, like, like),
        ).fetchall()
        return [
            SearchResult(
                id=str(row["id"] if hasattr(row, "keys") else row[0]),
                label=str(row["nombre"] if hasattr(row, "keys") else row[1]),
                subtitle=str(row["codigo"] if hasattr(row, "keys") else row[2] or ""),
                metadata={
                    "category": row["categoria"] if hasattr(row, "keys") else row[3],
                    "unit": row["unidad"] if hasattr(row, "keys") else row[4],
                    "price": row["precio"] if hasattr(row, "keys") else row[5],
                    "product_type": row["tipo_producto"] if hasattr(row, "keys") else row[6],
                },
            )
            for row in rows
        ]

    def list_rows(self, scope: str, filters: QueryFilters | None = None) -> Sequence[TableRow]:
        if scope != "products":
            return []
        filters = filters or {}
        params: list[Any] = []
        query = (
            "SELECT id, codigo, COALESCE(codigo_barras,'') AS codigo_barras, nombre, categoria, "
            "precio, COALESCE(existencia,0) AS existencia, COALESCE(activo,1) AS activo, tipo_producto "
            "FROM productos WHERE 1=1"
        )
        state = filters.get("state", "active")
        if state == "active":
            query += " AND COALESCE(activo,1)=1"
        elif state == "deleted":
            query += " AND COALESCE(activo,1)=0"
        category = str(filters.get("category") or "")
        if category:
            query += " AND categoria=?"
            params.append(category)
        text = str(filters.get("query") or "").strip()
        if text:
            query += " AND (nombre LIKE ? OR COALESCE(codigo,'') LIKE ? OR COALESCE(codigo_barras,'') LIKE ?)"
            like = f"%{text}%"
            params.extend([like, like, like])
        query += " ORDER BY activo DESC, nombre ASC LIMIT 1000"
        rows = self._connection.execute(query, params).fetchall()
        return [TableRow(id=str(self._value(row, "id", 0)), values=self._row_dict(row)) for row in rows]

    def metrics(self, scope: str, filters: QueryFilters | None = None) -> Sequence[KpiMetric]:
        if scope != "products":
            return []
        active = self._count("COALESCE(activo,1)=1")
        inactive = self._count("COALESCE(activo,1)=0")
        return [
            KpiMetric("activos", "Productos activos", active),
            KpiMetric("inactivos", "Inactivos", inactive),
        ]

    def list_categories(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT DISTINCT categoria FROM productos WHERE categoria IS NOT NULL AND categoria!='' ORDER BY categoria"
        ).fetchall()
        return [str(self._value(row, "categoria", 0)) for row in rows]

    def get_product(self, product_id: int | str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM productos WHERE id=?", (product_id,)).fetchone()
        return self._row_dict(row) if row is not None else None

    def find_duplicate_name(self, name: str, *, exclude_product_id: int | str | None = None) -> dict[str, Any] | None:
        params: list[Any] = [name]
        query = "SELECT id, codigo FROM productos WHERE LOWER(TRIM(nombre))=LOWER(TRIM(?)) AND COALESCE(activo,1)=1"
        if exclude_product_id:
            query += " AND id!=?"
            params.append(exclude_product_id)
        row = self._connection.execute(query, params).fetchone()
        return self._row_dict(row) if row is not None else None

    def _count(self, where: str) -> int:
        return int(self._connection.execute(f"SELECT COUNT(*) FROM productos WHERE {where}").fetchone()[0])

    @staticmethod
    def _value(row: Any, key: str, index: int) -> Any:
        return row[key] if hasattr(row, "keys") else row[index]

    @staticmethod
    def _row_dict(row: Any) -> dict[str, Any]:
        if hasattr(row, "keys"):
            return {key: row[key] for key in row.keys()}
        return dict(row)

logger = logging.getLogger("spj.products.query")

logger = logging.getLogger("spj.products.query")


class ProductQueryService(BaseQueryService):
    scope = "products"

    def __init__(self, data_source=None, db_conn: Any | None = None) -> None:
        super().__init__(data_source)
        self._db = db_conn

    @classmethod
    def from_connection(cls, db_conn: Any) -> "ProductQueryService":
        """Build a SQLite-backed product query service for legacy desktop wiring."""
        return cls(db_conn=db_conn)

    def search_products(self, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        return list(self.search(query, filters))

    def list_for_table(self, filters: QueryFilters | None = None) -> list[TableRow]:
        return list(self.list_rows(filters))

    def get_kpis(self, filters: QueryFilters | None = None) -> list[KpiMetric]:
        return list(self.metrics(filters))

    def list_catalog_rows(self, search: str = "", category: str = "", status_filter: int = 0, limit: int = 1000) -> list[dict]:
        """Return product catalog rows for the desktop table without SQL in UI.

        status_filter: 0 active, 1 inactive/deleted, 2 all.
        """
        if self._db is None:
            return []
        has_barcode = self._has_column("productos", "codigo_barras")
        barcode_expr = "COALESCE(codigo_barras,'')" if has_barcode else "''"
        query = (
            "SELECT id, codigo, "
            f"{barcode_expr} as codigo_barras, "
            "nombre, categoria, precio, existencia, COALESCE(activo,1) as activo "
            "FROM productos WHERE 1=1"
        )
        params: list[Any] = []
        if int(status_filter) == 0:
            query += " AND COALESCE(activo,1)=1"
        elif int(status_filter) == 1:
            query += " AND COALESCE(activo,1)=0"
        if category:
            query += " AND categoria=?"
            params.append(category)
        if search:
            query += f" AND (nombre LIKE ? OR codigo LIKE ? OR {barcode_expr} LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        query += " ORDER BY activo DESC, nombre ASC LIMIT ?"
        params.append(int(limit))
        try:
            rows = self._db.execute(query, params).fetchall()
        except Exception:
            logger.exception("Error listing product catalog rows")
            return []
        return [self._row_to_dict(row) for row in rows]

    def list_categories(self) -> list[str]:
        if self._db is None:
            return []
        try:
            rows = self._db.execute(
                "SELECT DISTINCT categoria FROM productos WHERE categoria IS NOT NULL ORDER BY categoria"
            ).fetchall()
        except Exception:
            logger.exception("Error listing product categories")
            return []
        return [str(row[0] if not hasattr(row, "keys") else row["categoria"]) for row in rows if (row[0] if not hasattr(row, "keys") else row["categoria"])]

    def get_product(self, product_id: int) -> dict | None:
        if self._db is None:
            return None
        try:
            row = self._db.execute("SELECT * FROM productos WHERE id = ?", (int(product_id),)).fetchone()
        except Exception:
            logger.exception("Error loading product_id=%s", product_id)
            return None
        return None if row is None else self._row_to_dict(row)

    def _has_column(self, table_name: str, column_name: str) -> bool:
        try:
            return any(str(row[1]) == column_name for row in self._db.execute(f"PRAGMA table_info({table_name})").fetchall())
        except Exception:
            logger.exception("Error checking %s.%s", table_name, column_name)
            return False

    @staticmethod
    def _row_to_dict(row: Any) -> dict:
        if hasattr(row, "keys"):
            return {key: row[key] for key in row.keys()}
        # Fallback for catalog query order.
        keys = ["id", "codigo", "codigo_barras", "nombre", "categoria", "precio", "existencia", "activo"]
        return {key: row[idx] if idx < len(row) else None for idx, key in enumerate(keys)}
