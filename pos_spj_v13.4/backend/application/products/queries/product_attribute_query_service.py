"""ProductAttributeQueryService — read side de atributos y opciones (P1-03).

Sirve la lista de atributos, sus opciones, y una vista combinada
``atributos-con-opciones`` que alimenta tanto la pantalla de gestión como el
selector de ejes/valores para la generación de variantes. Read-only.
"""

from __future__ import annotations


class ProductAttributeQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_attributes(self, *, active_only: bool = False) -> list[dict]:
        sql = ("SELECT id, code, name, data_type, active FROM product_attributes")
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY name"
        return [dict(r) for r in self._conn.execute(sql).fetchall()]

    def get(self, attribute_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, code, name, data_type, active FROM product_attributes "
            "WHERE id=?", (attribute_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_options(self, attribute_id: str, *, active_only: bool = False
                     ) -> list[dict]:
        sql = ("SELECT id, code, label, sort_order, active "
               "FROM product_attribute_options WHERE attribute_id=?")
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY sort_order, label"
        return [dict(r) for r in self._conn.execute(sql, (attribute_id,)).fetchall()]

    def get_option(self, option_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, attribute_id, code, label, sort_order, active "
            "FROM product_attribute_options WHERE id=?", (option_id,)).fetchone()
        return dict(row) if row is not None else None

    def attributes_with_options(self, *, active_only: bool = True) -> list[dict]:
        """Atributos LISTA con sus opciones anidadas (para elegir ejes de variante)."""
        result = []
        for attr in self.list_attributes(active_only=active_only):
            if attr["data_type"] != "LIST":
                continue
            attr = dict(attr)
            attr["options"] = self.list_options(attr["id"], active_only=active_only)
            result.append(attr)
        return result
