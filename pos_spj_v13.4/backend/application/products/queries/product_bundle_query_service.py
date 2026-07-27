"""ProductBundleQueryService — read side de combos/kits (§28). Read-only."""

from __future__ import annotations


class ProductBundleQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_bundles(self, product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, bundle_type, active FROM product_bundles "
            "WHERE product_id=? ORDER BY name", (product_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_versions(self, bundle_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, version_number, status FROM bundle_versions "
            "WHERE bundle_id=? ORDER BY version_number DESC", (bundle_id,)).fetchall()
        return [dict(r) for r in rows]

    def version_detail(self, version_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, bundle_id, version_number, status FROM bundle_versions "
            "WHERE id=?", (version_id,)).fetchone()
        if row is None:
            return None
        detail = dict(row)
        detail["components"] = [dict(r) for r in self._conn.execute(
            "SELECT id, component_product_id, quantity, unit_id, optional, "
            "substitutable, sequence FROM bundle_components WHERE version_id=? "
            "ORDER BY sequence", (version_id,)).fetchall()]
        return detail
