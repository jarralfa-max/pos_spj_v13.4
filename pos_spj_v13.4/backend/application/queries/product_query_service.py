"""Read-only QueryService for product UI/API read models."""

from __future__ import annotations

from typing import Any, Sequence

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


class ProductQueryService(BaseQueryService):
    scope = "products"

    @classmethod
    def from_connection(cls, connection: Any) -> "ProductQueryService":
        return cls(SQLiteProductQueryDataSource(connection))

    def search_products(self, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        return list(self.search(query, filters))

    def list_for_table(self, filters: QueryFilters | None = None) -> list[TableRow]:
        return list(self.list_rows(filters))

    def get_kpis(self, filters: QueryFilters | None = None) -> list[KpiMetric]:
        return list(self.metrics(filters))

    def list_categories(self) -> list[str]:
        data_source = self._data_source
        if hasattr(data_source, "list_categories"):
            return list(data_source.list_categories())
        return []

    def get_product(self, product_id: int | str) -> dict[str, Any] | None:
        data_source = self._data_source
        if hasattr(data_source, "get_product"):
            product = data_source.get_product(product_id)
            if product:
                self._apply_type_rules(product)
            return product
        return None

    def find_duplicate_name(self, name: str, *, exclude_product_id: int | str | None = None) -> dict[str, Any] | None:
        data_source = self._data_source
        if hasattr(data_source, "find_duplicate_name"):
            return data_source.find_duplicate_name(name, exclude_product_id=exclude_product_id)
        return None

    @staticmethod
    def type_labels_es() -> tuple[str, ...]:
        return ProductTypePolicy.spanish_labels()

    @staticmethod
    def type_help_es(product_type: str | None) -> str:
        return ProductTypePolicy.rules_for(product_type).help_es

    @staticmethod
    def type_rules(product_type: str | None) -> dict[str, Any]:
        rules = ProductTypePolicy.rules_for(product_type)
        return {
            "code": rules.code,
            "label_es": rules.label_es,
            "is_sellable": rules.is_sellable,
            "is_inventory_tracked": rules.is_inventory_tracked,
            "allows_recipe": rules.allows_recipe,
            "allows_virtual_stock": rules.allows_virtual_stock,
            "deducts_components_on_sale": rules.deducts_components_on_sale,
            "is_composite": rules.is_composite,
            "is_byproduct": rules.is_byproduct,
            "recipe_kind": rules.recipe_kind,
            "help_es": rules.help_es,
        }

    @staticmethod
    def _apply_type_rules(product: dict[str, Any]) -> None:
        rules = ProductTypePolicy.rules_for(product.get("tipo_producto"))
        product["type_rules"] = rules
