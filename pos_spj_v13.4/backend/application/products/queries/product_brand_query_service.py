"""ProductBrandQueryService — read side del catálogo de marcas (P1-02).

Sirve la lista para la pantalla de gestión y las opciones del selector del
formulario de producto (``{id, code, label}``, guarda siempre el UUID). Read-only.
"""

from __future__ import annotations


class ProductBrandQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_brands(self, *, active_only: bool = False) -> list[dict]:
        sql = "SELECT id, code, name, description, active FROM product_brands"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY name"
        return [{"id": r["id"], "code": r["code"], "name": r["name"],
                 "description": r["description"], "active": bool(r["active"])}
                for r in self._conn.execute(sql).fetchall()]

    def get(self, brand_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, code, name, description, active FROM product_brands WHERE id=?",
            (brand_id,)).fetchone()
        return dict(row) if row is not None else None

    def brand_exists(self, brand_id: str, *, active_only: bool = True) -> bool:
        sql = "SELECT 1 FROM product_brands WHERE id=?"
        if active_only:
            sql += " AND active=1"
        return self._conn.execute(sql + " LIMIT 1", (brand_id,)).fetchone() is not None

    def options(self, *, active_only: bool = True) -> list[dict]:
        """Opciones para el selector: ``{id, code, label}`` (label = nombre)."""
        return [{"id": b["id"], "code": b["code"], "label": b["name"]}
                for b in self.list_brands(active_only=active_only)]
