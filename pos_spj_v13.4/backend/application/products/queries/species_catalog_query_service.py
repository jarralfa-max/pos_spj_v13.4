"""SpeciesCatalogQueryService — read side del catálogo de especies (§5.2).

Sirve las opciones del selector de especie del formulario de producto
(``{id, code, label}``, guarda siempre el UUID) y la validación de existencia.
Read-only: sin escritura, sin commit. La tabla `species` la crea el esquema de
Productos (PROD-3) y la siembra la migración 169.
"""

from __future__ import annotations


class SpeciesCatalogQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _table_exists(self) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='species'"
        ).fetchone() is not None

    def list_species(self, *, active_only: bool = True) -> list[dict]:
        if not self._table_exists():
            return []
        sql = "SELECT id, code, name, active FROM species"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY name"
        return [{"id": r["id"], "code": r["code"], "name": r["name"],
                 "active": bool(r["active"])}
                for r in self._conn.execute(sql).fetchall()]

    def get(self, species_id: str) -> dict | None:
        if not self._table_exists():
            return None
        row = self._conn.execute(
            "SELECT id, code, name, active FROM species WHERE id=?",
            (species_id,)).fetchone()
        return dict(row) if row is not None else None

    def species_exists(self, species_id: str, *, active_only: bool = True) -> bool:
        if not species_id or not self._table_exists():
            return False
        sql = "SELECT 1 FROM species WHERE id=?"
        if active_only:
            sql += " AND active=1"
        return self._conn.execute(sql + " LIMIT 1", (species_id,)).fetchone() is not None

    def options(self, *, active_only: bool = True) -> list[dict]:
        """Opciones para el selector: ``{id, code, label}`` (label = nombre)."""
        return [{"id": s["id"], "code": s["code"], "label": s["name"]}
                for s in self.list_species(active_only=active_only)]
