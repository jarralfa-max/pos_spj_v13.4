"""YieldRepository — persistence for yield profiles / versions / outputs (PROD-10).

Decimal ↔ str; loads a version with its outputs. Never commits (the caller owns the
transaction). Exposes the ACTIVE version for a given input product (used by the
future slaughter/production modules, §25/§32).
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.products.entities.yield_output import YieldOutput
from backend.domain.products.entities.yield_profile import YieldProfile
from backend.domain.products.entities.yield_profile_version import YieldProfileVersion
from backend.domain.products.recipe_enums import OutputType, RecipeVersionStatus


def _od(v: str | None) -> Decimal | None:
    return None if v is None else Decimal(v)


class YieldRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def save_profile(self, profile: YieldProfile) -> None:
        self._conn.execute(
            """INSERT INTO yield_profiles (id, input_product_id, species_id, name, active)
               VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, active=excluded.active""",
            (profile.id, profile.input_product_id, profile.species_id, profile.name,
             int(profile.active)))

    def get_profile(self, profile_id: str) -> YieldProfile | None:
        row = self._conn.execute(
            "SELECT * FROM yield_profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            return None
        return YieldProfile(id=row["id"], input_product_id=row["input_product_id"],
                            species_id=row["species_id"], name=row["name"],
                            active=bool(row["active"]))

    def save_version(self, version: YieldProfileVersion) -> None:
        self._conn.execute(
            """INSERT INTO yield_profile_versions
               (id, yield_profile_id, version_number, status, tolerance_pct,
                effective_from, effective_to, approved_by_user_id, reason)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 status=excluded.status, tolerance_pct=excluded.tolerance_pct,
                 effective_from=excluded.effective_from, effective_to=excluded.effective_to,
                 approved_by_user_id=excluded.approved_by_user_id, reason=excluded.reason""",
            (version.id, version.yield_profile_id, version.version_number,
             version.status.value, str(version.tolerance_pct),
             version.effective_from, version.effective_to,
             version.approved_by_user_id, version.reason))
        self._conn.execute("DELETE FROM yield_outputs WHERE version_id=?", (version.id,))
        for o in version.outputs:
            self._conn.execute(
                """INSERT INTO yield_outputs
                   (id, version_id, product_id, output_type, expected_yield_pct,
                    expected_quantity, minimum_yield_pct, maximum_yield_pct, unit_id,
                    cost_allocation_weight, sequence)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (o.id, version.id, o.product_id, o.output_type.value,
                 str(o.expected_yield_pct), str(o.expected_quantity),
                 None if o.minimum_yield_pct is None else str(o.minimum_yield_pct),
                 None if o.maximum_yield_pct is None else str(o.maximum_yield_pct),
                 o.unit_id, str(o.cost_allocation_weight), o.sequence))

    def get_version(self, version_id: str) -> YieldProfileVersion | None:
        row = self._conn.execute(
            "SELECT * FROM yield_profile_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            return None
        version = YieldProfileVersion(
            id=row["id"], yield_profile_id=row["yield_profile_id"],
            version_number=row["version_number"],
            status=RecipeVersionStatus(row["status"]),
            tolerance_pct=Decimal(row["tolerance_pct"]),
            effective_from=row["effective_from"], effective_to=row["effective_to"],
            approved_by_user_id=row["approved_by_user_id"], reason=row["reason"])
        version.outputs = [
            YieldOutput(id=r["id"], version_id=r["version_id"], product_id=r["product_id"],
                        output_type=OutputType(r["output_type"]),
                        expected_yield_pct=Decimal(r["expected_yield_pct"]),
                        expected_quantity=Decimal(r["expected_quantity"]),
                        minimum_yield_pct=_od(r["minimum_yield_pct"]),
                        maximum_yield_pct=_od(r["maximum_yield_pct"]),
                        unit_id=r["unit_id"],
                        cost_allocation_weight=Decimal(r["cost_allocation_weight"]),
                        sequence=r["sequence"])
            for r in self._conn.execute(
                "SELECT * FROM yield_outputs WHERE version_id=? ORDER BY sequence",
                (version_id,)).fetchall()]
        return version

    def active_version_for_input(self, input_product_id: str) -> YieldProfileVersion | None:
        row = self._conn.execute(
            """SELECT v.id FROM yield_profile_versions v
               JOIN yield_profiles p ON p.id = v.yield_profile_id
               WHERE p.input_product_id=? AND v.status='ACTIVE'
               ORDER BY v.version_number DESC LIMIT 1""", (input_product_id,)).fetchone()
        return self.get_version(row["id"]) if row else None
