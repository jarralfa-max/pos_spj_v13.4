"""MeatClassificationQueryService (PROD-3) — read side de regiones anatómicas y
cortes por especie.

Sirve las opciones de los selectores del formulario cárnico (``{id, code,
label}``) y la validación de existencia. Read-only: sin escritura, sin commit.
Especies tienen su propio read service (``SpeciesCatalogQueryService``).
"""

from __future__ import annotations


class MeatClassificationQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── regiones anatómicas ──────────────────────────────────────────────
    def list_regions(self, species_id: str, *, active_only: bool = True) -> list[dict]:
        sql = "SELECT id, species_id, code, name, active FROM anatomical_regions WHERE species_id=?"
        params: list = [species_id]
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY name"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def region_options(self, species_id: str, *, active_only: bool = True) -> list[dict]:
        return [{"id": r["id"], "code": r["code"], "label": r["name"]}
                for r in self.list_regions(species_id, active_only=active_only)]

    # ── cortes ────────────────────────────────────────────────────────────
    def list_cuts(self, species_id: str, *, active_only: bool = True) -> list[dict]:
        sql = ("SELECT id, species_id, anatomical_region_id, code, name, cut_level, "
              "bone_status, fat_class, quality_grade, parent_cut_id, status "
              "FROM cut_classifications WHERE species_id=?")
        params: list = [species_id]
        if active_only:
            sql += " AND status='ACTIVE'"
        sql += " ORDER BY cut_level, name"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def cut_options(self, species_id: str, *, active_only: bool = True) -> list[dict]:
        return [{"id": c["id"], "code": c["code"], "label": c["name"],
                 "cut_level": c["cut_level"]}
                for c in self.list_cuts(species_id, active_only=active_only)]

    def cut_hierarchy(self, species_id: str, *, active_only: bool = True) -> list[dict]:
        """Cortes con su cadena de niveles, para renderizar el árbol
        canal → primario → secundario → porcionado en la UI."""
        return self.list_cuts(species_id, active_only=active_only)
