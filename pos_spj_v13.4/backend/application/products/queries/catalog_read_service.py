"""ProductCatalogReadService — read side for the enterprise products UI (§43).

Returns display rows and overview counts for the module. Read-only, parametrized
SQL over the canonical products schema. The presenter/UI never issues SQL — they
consume these results.
"""

from __future__ import annotations

from backend.domain.products.enums import MEAT_PRODUCT_TYPES

_MEAT_VALUES = tuple(t.value for t in MEAT_PRODUCT_TYPES)
_MEAT_PLACEHOLDERS = ",".join("?" for _ in _MEAT_VALUES)


class ProductCatalogReadService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def overview_counts(self) -> dict:
        c = self._conn
        active = c.execute(
            "SELECT COUNT(*) FROM products WHERE lifecycle_status='ACTIVE'").fetchone()[0]
        meat = c.execute(
            f"SELECT COUNT(*) FROM products WHERE product_type IN ({_MEAT_PLACEHOLDERS})",
            _MEAT_VALUES).fetchone()[0]
        internal = c.execute(
            "SELECT COUNT(*) FROM products WHERE internal_only=1").fetchone()[0]
        incomplete = c.execute(
            f"""SELECT COUNT(*) FROM products
                WHERE category_id IS NULL OR base_unit_id IS NULL OR base_unit_id=''
                   OR (product_type IN ({_MEAT_PLACEHOLDERS})
                       AND (species_id IS NULL OR species_id=''))""",
            _MEAT_VALUES).fetchone()[0]
        recipes_unapproved = c.execute(
            "SELECT COUNT(*) FROM recipe_versions WHERE status IN ('DRAFT','UNDER_REVIEW')"
        ).fetchone()[0]
        yield_pending = c.execute(
            "SELECT COUNT(*) FROM yield_profile_versions "
            "WHERE status IN ('DRAFT','UNDER_REVIEW')").fetchone()[0]
        return {"active": active, "meat": meat, "internal": internal,
                "incomplete": incomplete, "recipes_unapproved": recipes_unapproved,
                "yield_pending": yield_pending}

    def list_catalog(self, *, query: str | None = None, product_type: str | None = None,
                     limit: int = 200) -> list[dict]:
        sql = ("SELECT id, code, name, product_type, lifecycle_status, species_id "
               "FROM products WHERE 1=1")
        params: list = []
        if query:
            sql += " AND (name_normalized LIKE ? OR code LIKE ?)"
            needle = f"%{query.strip().lower()}%"
            params += [needle, f"%{query.strip().upper()}%"]
        if product_type:
            sql += " AND product_type=?"
            params.append(product_type)
        sql += " ORDER BY name LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [{"id": r["id"], "code": r["code"], "name": r["name"],
                 "product_type": r["product_type"],
                 "lifecycle_status": r["lifecycle_status"],
                 "is_meat": r["product_type"] in _MEAT_VALUES} for r in rows]

    def list_recent_alerts(self, *, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT entity_id, severity, alert_type, message FROM product_notification_log "
            "WHERE status='SENT' ORDER BY created_at DESC LIMIT ?", (int(limit),)).fetchall()
        return [{"entity_id": r["entity_id"], "severity": r["severity"],
                 "alert_type": r["alert_type"], "message": r["message"]} for r in rows]
