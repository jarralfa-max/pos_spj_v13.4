"""Directorios de clientes y proveedores vistos desde Finanzas (sólo lectura).

Leen los maestros canónicos (``customers`` de CRM/Clientes y ``proveedores``
de Compras/Proveedores). Implementan ``PartyDirectoryPort``.
"""

from __future__ import annotations


class _Directory:
    _sql_names = ""
    _sql_search = ""

    def __init__(self, connection) -> None:
        self._conn = connection

    def display_names(self, ids: list[str]) -> dict[str, str]:
        ids = [str(i) for i in dict.fromkeys(ids) if i]
        if not ids:
            return {}
        marks = ",".join("?" for _ in ids)
        rows = self._conn.execute(self._sql_names.format(marks=marks), tuple(ids)).fetchall()
        return {str(row[0]): str(row[1] or "") for row in rows if row[1]}

    def search(self, text: str, limit: int = 20) -> list[dict]:
        pattern = f"%{(text or '').strip()}%"
        rows = self._conn.execute(self._sql_search, (pattern, limit)).fetchall()
        return [{"id": str(row[0]), "name": str(row[1] or "")} for row in rows]


class SqliteCustomerDirectory(_Directory):
    _sql_names = "SELECT id, display_name FROM customers WHERE id IN ({marks})"
    _sql_search = ("SELECT id, display_name FROM customers WHERE display_name LIKE ?"
                   " ORDER BY display_name LIMIT ?")


class SqliteSupplierNameDirectory(_Directory):
    _sql_names = "SELECT id, nombre FROM proveedores WHERE id IN ({marks})"
    _sql_search = ("SELECT id, nombre FROM proveedores WHERE nombre LIKE ? AND activo=1"
                   " ORDER BY nombre LIMIT ?")


class NoPartyNames:
    """Sin directorio (contexto financiero aislado): no hay nombres que mostrar."""

    def display_names(self, ids: list[str]) -> dict[str, str]:
        return {}

    def search(self, text: str, limit: int = 20) -> list[dict]:
        return []

    def category_names(self, ids: list[str]) -> dict[str, str]:
        return {}

    def categories_of(self, product_ids: list[str]) -> dict[str, str]:
        return {}


class SqliteProductDirectory(_Directory):
    """Productos y categorías del catálogo canónico (Productos)."""

    _sql_names = "SELECT id, name FROM products WHERE id IN ({marks})"
    _sql_search = ("SELECT id, name FROM products WHERE name LIKE ? ORDER BY name LIMIT ?")

    def category_names(self, ids: list[str]) -> dict[str, str]:
        ids = [str(i) for i in dict.fromkeys(ids) if i]
        if not ids:
            return {}
        marks = ",".join("?" for _ in ids)
        rows = self._conn.execute(
            f"SELECT id, name FROM product_categories WHERE id IN ({marks})", tuple(ids)).fetchall()
        return {str(r[0]): str(r[1] or "") for r in rows}

    def categories_of(self, product_ids: list[str]) -> dict[str, str]:
        ids = [str(i) for i in dict.fromkeys(product_ids) if i]
        if not ids:
            return {}
        marks = ",".join("?" for _ in ids)
        rows = self._conn.execute(
            f"SELECT id, category_id FROM products WHERE id IN ({marks})", tuple(ids)).fetchall()
        return {str(r[0]): str(r[1]) for r in rows if r[1]}
