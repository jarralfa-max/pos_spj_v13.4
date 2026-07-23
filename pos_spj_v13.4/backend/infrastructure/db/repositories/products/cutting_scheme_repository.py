"""CuttingSchemeRepository — persistence for cutting schemes/versions/outputs (PROD-11).

Decimal ↔ str; loads a version with its outputs. Never commits. Exposes the ACTIVE
version for a given input product (used by the future slaughter module, §25).
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.products.entities.cutting_output import CuttingOutput, MeasureKind
from backend.domain.products.entities.cutting_scheme import CuttingScheme
from backend.domain.products.entities.cutting_scheme_version import (
    CuttingSchemeVersion,
)
from backend.domain.products.meat_enums import BoneStatus, CutLevel
from backend.domain.products.recipe_enums import OutputType, RecipeVersionStatus


class CuttingSchemeRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def save_scheme(self, scheme: CuttingScheme) -> None:
        self._conn.execute(
            """INSERT INTO cutting_schemes
               (id, input_product_id, species_id, name, cut_level, active)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                 cut_level=excluded.cut_level, active=excluded.active""",
            (scheme.id, scheme.input_product_id, scheme.species_id, scheme.name,
             scheme.cut_level.value, int(scheme.active)))

    def get_scheme(self, scheme_id: str) -> CuttingScheme | None:
        row = self._conn.execute(
            "SELECT * FROM cutting_schemes WHERE id=?", (scheme_id,)).fetchone()
        if row is None:
            return None
        return CuttingScheme(id=row["id"], input_product_id=row["input_product_id"],
                             species_id=row["species_id"], name=row["name"],
                             cut_level=CutLevel(row["cut_level"]), active=bool(row["active"]))

    def save_version(self, version: CuttingSchemeVersion) -> None:
        self._conn.execute(
            """INSERT INTO cutting_scheme_versions
               (id, cutting_scheme_id, version_number, status, effective_from,
                effective_to, approved_by_user_id, reason)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 status=excluded.status, effective_from=excluded.effective_from,
                 effective_to=excluded.effective_to,
                 approved_by_user_id=excluded.approved_by_user_id, reason=excluded.reason""",
            (version.id, version.cutting_scheme_id, version.version_number,
             version.status.value, version.effective_from, version.effective_to,
             version.approved_by_user_id, version.reason))
        self._conn.execute("DELETE FROM cutting_outputs WHERE version_id=?", (version.id,))
        for o in version.outputs:
            self._conn.execute(
                """INSERT INTO cutting_outputs
                   (id, version_id, product_id, output_type, measure_kind, quantity,
                    unit_id, cut_classification_id, cut_level, bone_status, sequence)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (o.id, version.id, o.product_id, o.output_type.value,
                 o.measure_kind.value, str(o.quantity), o.unit_id,
                 o.cut_classification_id,
                 None if o.cut_level is None else o.cut_level.value,
                 o.bone_status.value, o.sequence))

    def get_version(self, version_id: str) -> CuttingSchemeVersion | None:
        row = self._conn.execute(
            "SELECT * FROM cutting_scheme_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            return None
        version = CuttingSchemeVersion(
            id=row["id"], cutting_scheme_id=row["cutting_scheme_id"],
            version_number=row["version_number"],
            status=RecipeVersionStatus(row["status"]),
            effective_from=row["effective_from"], effective_to=row["effective_to"],
            approved_by_user_id=row["approved_by_user_id"], reason=row["reason"])
        version.outputs = [
            CuttingOutput(id=r["id"], version_id=r["version_id"], product_id=r["product_id"],
                          output_type=OutputType(r["output_type"]),
                          measure_kind=MeasureKind(r["measure_kind"]),
                          quantity=Decimal(r["quantity"]), unit_id=r["unit_id"],
                          cut_classification_id=r["cut_classification_id"],
                          cut_level=(None if r["cut_level"] is None else CutLevel(r["cut_level"])),
                          bone_status=BoneStatus(r["bone_status"]), sequence=r["sequence"])
            for r in self._conn.execute(
                "SELECT * FROM cutting_outputs WHERE version_id=? ORDER BY sequence",
                (version_id,)).fetchall()]
        return version

    def active_version_for_input(self, input_product_id: str) -> CuttingSchemeVersion | None:
        row = self._conn.execute(
            """SELECT v.id FROM cutting_scheme_versions v
               JOIN cutting_schemes s ON s.id = v.cutting_scheme_id
               WHERE s.input_product_id=? AND v.status='ACTIVE'
               ORDER BY v.version_number DESC LIMIT 1""", (input_product_id,)).fetchone()
        return self.get_version(row["id"]) if row else None
