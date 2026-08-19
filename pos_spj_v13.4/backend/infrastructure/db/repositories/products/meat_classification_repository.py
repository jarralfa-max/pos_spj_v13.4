"""MeatClassificationRepository (PROD-3) — persistencia de especies, regiones
anatómicas y cortes.

Escritura parametrizada, sin commit (el caso de uso es dueño de la transacción).
Especies y regiones usan una bandera ``active`` booleana; los cortes usan
``status`` (``LifecycleStatus``, coherente con el resto del catálogo de
Productos que versiona/activa por estado, no por bandera).
"""

from __future__ import annotations

from backend.domain.products.entities.anatomical_region import AnatomicalRegion
from backend.domain.products.entities.cut_classification import CutClassification
from backend.domain.products.entities.species import Species
from backend.domain.products.enums import LifecycleStatus
from backend.domain.products.meat_enums import BoneStatus, CutLevel, FatClass


def _species(row) -> Species:
    return Species(id=row["id"], code=row["code"], name=row["name"],
                  active=bool(row["active"]))


def _region(row) -> AnatomicalRegion:
    return AnatomicalRegion(id=row["id"], species_id=row["species_id"],
                            code=row["code"], name=row["name"],
                            active=bool(row["active"]))


def _cut(row) -> CutClassification:
    return CutClassification(
        id=row["id"], species_id=row["species_id"],
        anatomical_region_id=row["anatomical_region_id"], code=row["code"],
        name=row["name"], cut_level=CutLevel(row["cut_level"]),
        bone_status=BoneStatus(row["bone_status"]), fat_class=FatClass(row["fat_class"]),
        quality_grade=row["quality_grade"], parent_cut_id=row["parent_cut_id"],
        status=LifecycleStatus(row["status"]))


class MeatClassificationRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── especies ──────────────────────────────────────────────────────────
    def get_species(self, species_id: str) -> Species | None:
        row = self._conn.execute(
            "SELECT * FROM species WHERE id=?", (species_id,)).fetchone()
        return _species(row) if row is not None else None

    def species_code_exists(self, code: str, *, exclude_id: str | None = None) -> bool:
        sql = "SELECT 1 FROM species WHERE code=?"
        params: list = [(code or "").strip().upper()]
        if exclude_id:
            sql += " AND id<>?"
            params.append(exclude_id)
        return self._conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    def list_species(self, *, active_only: bool = False) -> list[Species]:
        sql = "SELECT * FROM species"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY name"
        return [_species(r) for r in self._conn.execute(sql).fetchall()]

    def save_species(self, species: Species) -> None:
        self._conn.execute(
            "INSERT INTO species (id, code, name, active) VALUES (?,?,?,?)",
            (species.id, species.code, species.name, 1 if species.active else 0))

    def set_species_active(self, species_id: str, active: bool) -> None:
        self._conn.execute(
            "UPDATE species SET active=?, updated_at=datetime('now') WHERE id=?",
            (1 if active else 0, species_id))

    # ── regiones anatómicas ───────────────────────────────────────────────
    def get_region(self, region_id: str) -> AnatomicalRegion | None:
        row = self._conn.execute(
            "SELECT * FROM anatomical_regions WHERE id=?", (region_id,)).fetchone()
        return _region(row) if row is not None else None

    def region_code_exists(self, species_id: str, code: str, *,
                           exclude_id: str | None = None) -> bool:
        sql = "SELECT 1 FROM anatomical_regions WHERE species_id=? AND code=?"
        params: list = [species_id, (code or "").strip().upper()]
        if exclude_id:
            sql += " AND id<>?"
            params.append(exclude_id)
        return self._conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    def list_regions(self, species_id: str, *, active_only: bool = False) \
            -> list[AnatomicalRegion]:
        sql = "SELECT * FROM anatomical_regions WHERE species_id=?"
        params: list = [species_id]
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY name"
        return [_region(r) for r in self._conn.execute(sql, params).fetchall()]

    def save_region(self, region: AnatomicalRegion) -> None:
        self._conn.execute(
            "INSERT INTO anatomical_regions (id, species_id, code, name, active) "
            "VALUES (?,?,?,?,?)",
            (region.id, region.species_id, region.code, region.name,
             1 if region.active else 0))

    def set_region_active(self, region_id: str, active: bool) -> None:
        self._conn.execute(
            "UPDATE anatomical_regions SET active=? WHERE id=?",
            (1 if active else 0, region_id))

    # ── cortes ────────────────────────────────────────────────────────────
    def get_cut(self, cut_id: str) -> CutClassification | None:
        row = self._conn.execute(
            "SELECT * FROM cut_classifications WHERE id=?", (cut_id,)).fetchone()
        return _cut(row) if row is not None else None

    def cut_code_exists(self, species_id: str, code: str, *,
                        exclude_id: str | None = None) -> bool:
        sql = "SELECT 1 FROM cut_classifications WHERE species_id=? AND code=?"
        params: list = [species_id, (code or "").strip().upper()]
        if exclude_id:
            sql += " AND id<>?"
            params.append(exclude_id)
        return self._conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    def list_cuts(self, species_id: str, *, active_only: bool = False) \
            -> list[CutClassification]:
        sql = "SELECT * FROM cut_classifications WHERE species_id=?"
        params: list = [species_id]
        if active_only:
            sql += " AND status='ACTIVE'"
        sql += " ORDER BY cut_level, name"
        return [_cut(r) for r in self._conn.execute(sql, params).fetchall()]

    def save_cut(self, cut: CutClassification) -> None:
        self._conn.execute(
            "INSERT INTO cut_classifications (id, species_id, anatomical_region_id, "
            "code, name, cut_level, bone_status, fat_class, quality_grade, "
            "parent_cut_id, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (cut.id, cut.species_id, cut.anatomical_region_id, cut.code, cut.name,
             cut.cut_level.value, cut.bone_status.value, cut.fat_class.value,
             cut.quality_grade, cut.parent_cut_id, cut.status.value))

    def set_cut_status(self, cut_id: str, status: LifecycleStatus) -> None:
        self._conn.execute(
            "UPDATE cut_classifications SET status=? WHERE id=?",
            (status.value, cut_id))
