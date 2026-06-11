"""SQLite-backed repository for the product catalog canonical route."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ProductRepository:
    """Owns product persistence details for catalog use cases."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        try:
            import sqlite3
            if getattr(self._connection, "row_factory", None) is None:
                self._connection.row_factory = sqlite3.Row
        except Exception:
            pass

    def get_by_id(self, product_id: int | str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM productos WHERE id=?", (product_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_categories(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT DISTINCT categoria FROM productos WHERE categoria IS NOT NULL AND categoria!='' ORDER BY categoria"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def sku_exists(self, sku: str, *, exclude_product_id: int | str | None = None) -> dict[str, Any] | None:
        if exclude_product_id:
            row = self._connection.execute(
                "SELECT id, nombre FROM productos WHERE codigo=? AND id!=?",
                (sku, exclude_product_id),
            ).fetchone()
        else:
            row = self._connection.execute("SELECT id, nombre FROM productos WHERE codigo=?", (sku,)).fetchone()
        return dict(row) if row is not None else None

    def active_name_duplicate(self, name: str, *, exclude_product_id: int | str | None = None) -> dict[str, Any] | None:
        params: list[Any] = [name]
        query = "SELECT id, codigo FROM productos WHERE LOWER(TRIM(nombre))=LOWER(TRIM(?)) AND COALESCE(activo,1)=1"
        if exclude_product_id:
            query += " AND id!=?"
            params.append(exclude_product_id)
        row = self._connection.execute(query, params).fetchone()
        return dict(row) if row is not None else None

    def has_active_recipe(self, product_id: int | str) -> bool:
        try:
            row = self._connection.execute(
                "SELECT id FROM product_recipes WHERE base_product_id=? AND is_active=1",
                (product_id,),
            ).fetchone()
        except Exception:
            return False
        return row is not None

    def create(self, product_data: dict[str, Any]) -> str:
        cursor = self._connection.execute(
            """
            INSERT INTO productos (
                nombre, codigo, codigo_barras, categoria, precio, precio_compra,
                precio_minimo_venta, unidad, stock_minimo, tipo_producto, es_compuesto,
                es_subproducto, imagen_path, existencia, oculto, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (
                product_data["name"],
                product_data["sku"],
                product_data["barcode"],
                product_data["category"],
                product_data["sale_price"],
                product_data["purchase_price"],
                product_data["minimum_sale_price"],
                product_data["unit"],
                product_data["minimum_stock"],
                product_data["product_type"],
                product_data["is_composite"],
                product_data["is_byproduct"],
                product_data["image_path"],
                1 if product_data["active"] else 0,
            ),
        )
        return str(cursor.lastrowid)

    def update(self, product_id: int | str, product_data: dict[str, Any]) -> str:
        updated_at = datetime.now(timezone.utc).isoformat()
        self._connection.execute(
            """
            UPDATE productos SET
                nombre=?, codigo=?, codigo_barras=?, categoria=?, precio=?, precio_compra=?,
                precio_minimo_venta=?, unidad=?, stock_minimo=?, tipo_producto=?,
                es_compuesto=?, es_subproducto=?, activo=?, imagen_path=?,
                ultima_actualizacion=?
            WHERE id=?
            """,
            (
                product_data["name"],
                product_data["sku"],
                product_data["barcode"],
                product_data["category"],
                product_data["sale_price"],
                product_data["purchase_price"],
                product_data["minimum_sale_price"],
                product_data["unit"],
                product_data["minimum_stock"],
                product_data["product_type"],
                product_data["is_composite"],
                product_data["is_byproduct"],
                1 if product_data["active"] else 0,
                product_data["image_path"],
                updated_at,
                product_id,
            ),
        )
        return str(product_id)

    def save_changes(self) -> None:
        self._connection.commit()

    def rollback_changes(self) -> None:
        self._connection.rollback()
