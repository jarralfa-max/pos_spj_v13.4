"""ProductCategoryQueryService — read side del árbol de categorías (P1-01).

Sirve dos vistas: el **árbol** anidado para la pantalla de gestión, y una lista
**plana con sangría** (``label`` = "— — Nombre") para el selector del formulario de
producto, guardando siempre el ``product_categories.id`` (UUID), nunca el texto.
Read-only, parametrizado.
"""

from __future__ import annotations


class ProductCategoryQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _rows(self, *, active_only: bool):
        sql = ("SELECT id, code, name, parent_id, depth, sort_order, active "
               "FROM product_categories")
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY depth, sort_order, name"
        return self._conn.execute(sql).fetchall()

    def category_exists(self, category_id: str, *, active_only: bool = True) -> bool:
        sql = "SELECT 1 FROM product_categories WHERE id=?"
        if active_only:
            sql += " AND active=1"
        return self._conn.execute(sql + " LIMIT 1", (category_id,)).fetchone() is not None

    def get(self, category_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, code, name, parent_id, depth, path, sort_order, active "
            "FROM product_categories WHERE id=?", (category_id,)).fetchone()
        return dict(row) if row is not None else None

    def tree(self, *, active_only: bool = False) -> list[dict]:
        """Árbol anidado: cada nodo ``{id, code, name, active, depth, children:[…]}``."""
        rows = self._rows(active_only=active_only)
        nodes = {r["id"]: {"id": r["id"], "code": r["code"], "name": r["name"],
                           "active": bool(r["active"]), "depth": int(r["depth"]),
                           "parent_id": r["parent_id"], "children": []} for r in rows}
        roots: list[dict] = []
        for node in nodes.values():
            parent = nodes.get(node["parent_id"])
            (parent["children"] if parent else roots).append(node)
        return roots

    def flat_options(self, *, active_only: bool = True) -> list[dict]:
        """Lista plana ordenada por jerarquía para el selector: ``{id, code, label}``.

        El ``label`` sangra por profundidad para reflejar el nivel sin perder que el
        valor guardado es el UUID.
        """
        options: list[dict] = []

        def walk(nodes: list[dict]) -> None:
            for n in sorted(nodes, key=lambda x: x["name"].lower()):
                indent = "   " * n["depth"]
                options.append({"id": n["id"], "code": n["code"],
                                "label": f"{indent}{n['name']}"})
                walk(n["children"])

        walk(self.tree(active_only=active_only))
        return options

    def breadcrumb(self, category_id: str) -> list[dict]:
        """Ruta raíz→hoja de una categoría como ``[{id, name}, …]``."""
        row = self.get(category_id)
        if row is None:
            return []
        ids = [seg for seg in (row["path"] or "").split("/") if seg]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        found = {r["id"]: r["name"] for r in self._conn.execute(
            f"SELECT id, name FROM product_categories WHERE id IN ({placeholders})",
            ids).fetchall()}
        return [{"id": cid, "name": found.get(cid, "")} for cid in ids]
