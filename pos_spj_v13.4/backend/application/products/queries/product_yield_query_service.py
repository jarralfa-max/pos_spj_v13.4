"""ProductYieldQueryService — read side de rendimientos (yields). Read-only.

Sirve los perfiles de rendimiento de un producto de entrada, sus versiones y el
detalle (outputs) de una versión para la pantalla de gestión.
"""

from __future__ import annotations


class ProductYieldQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_profiles(self, input_product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, species_id, active FROM yield_profiles "
            "WHERE input_product_id=? ORDER BY name", (input_product_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_versions(self, profile_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, version_number, status, tolerance_pct, created_by "
            "FROM yield_profile_versions WHERE yield_profile_id=? "
            "ORDER BY version_number DESC", (profile_id,)).fetchall()
        return [dict(r) for r in rows]

    def version_detail(self, version_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, yield_profile_id, version_number, status, tolerance_pct, "
            "created_by FROM yield_profile_versions WHERE id=?",
            (version_id,)).fetchone()
        if row is None:
            return None
        detail = dict(row)
        detail["outputs"] = [dict(r) for r in self._conn.execute(
            "SELECT id, product_id, output_type, expected_yield_pct, "
            "minimum_yield_pct, maximum_yield_pct, unit_id, sequence "
            "FROM yield_outputs WHERE version_id=? ORDER BY sequence",
            (version_id,)).fetchall()]
        return detail
