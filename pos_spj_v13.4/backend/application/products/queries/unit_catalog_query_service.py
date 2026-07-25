"""UnitCatalogQueryService — read side del catálogo de unidades (P0-03).

Sirve el selector de unidad del formulario de producto: devuelve unidades activas
como ``{id, code, name, dimension}`` para mostrar "CODE — Name" y guardar el
``units_of_measure.id`` (UUID), nunca el texto. Read-only, parametrizado.
"""

from __future__ import annotations


class UnitCatalogQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_units(self, *, dimension: str | None = None, active_only: bool = True
                   ) -> list[dict]:
        sql = ("SELECT id, code, name, dimension, active FROM units_of_measure "
               "WHERE 1=1")
        params: list = []
        if active_only:
            sql += " AND active=1"
        if dimension:
            sql += " AND dimension=?"
            params.append(dimension)
        sql += " ORDER BY dimension, code"
        rows = self._conn.execute(sql, params).fetchall()
        return [{"id": r["id"], "code": r["code"], "name": r["name"],
                 "dimension": r["dimension"]} for r in rows]

    def get_unit(self, unit_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, code, name, dimension FROM units_of_measure WHERE id=?",
            (unit_id,)).fetchone()
        return dict(row) if row is not None else None

    def unit_exists(self, unit_id: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM units_of_measure WHERE id=? AND active=1 LIMIT 1",
            (unit_id,)).fetchone() is not None
