"""ProductCuttingQueryService — read side de esquemas de despiece. Read-only."""

from __future__ import annotations


class ProductCuttingQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_schemes(self, input_product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, species_id, cut_level, active FROM cutting_schemes "
            "WHERE input_product_id=? ORDER BY name", (input_product_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_versions(self, scheme_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, version_number, status FROM cutting_scheme_versions "
            "WHERE cutting_scheme_id=? ORDER BY version_number DESC",
            (scheme_id,)).fetchall()
        return [dict(r) for r in rows]

    def version_detail(self, version_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, cutting_scheme_id, version_number, status "
            "FROM cutting_scheme_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            return None
        detail = dict(row)
        detail["outputs"] = [dict(r) for r in self._conn.execute(
            "SELECT id, product_id, output_type, measure_kind, quantity, unit_id, "
            "cut_level, sequence FROM cutting_outputs WHERE version_id=? "
            "ORDER BY sequence", (version_id,)).fetchall()]
        return detail
