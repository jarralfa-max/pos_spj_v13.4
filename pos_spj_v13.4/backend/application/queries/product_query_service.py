"""Read-only QueryService for the products UI/API read models."""

from __future__ import annotations

import logging
from typing import Any

from backend.application.queries.base_query_service import BaseQueryService, KpiMetric, QueryFilters, SearchResult, TableRow

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
