"""ExternalCatalogQueryService (PROD-22, §15) — fuentes y registros externos en revisión.

Read side de la sección «Catálogo externo». Los registros vienen de una búsqueda
(Open Food Facts, proveedor, CSV) y esperan revisión antes de importarse; nunca
entran al maestro sin que alguien los apruebe. Read-only.
"""

from __future__ import annotations


class ExternalCatalogQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def sources(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, code, name, provider_type FROM external_catalog_sources "
            "WHERE active=1 ORDER BY name").fetchall()
        return [{"id": r[0], "code": r[1], "name": r[2], "provider_type": r[3]}
                for r in rows]

    def records(self, *, status: str | None = None, limit: int = 300) -> list[dict]:
        sql = ("SELECT r.id, r.name, r.brand, r.barcode, r.category, r.net_weight, r.unit, "
               "r.status, r.data_quality_score, r.matched_product_id, p.code, p.name, "
               "s.name, r.created_at "
               "FROM external_product_records r "
               "LEFT JOIN products p ON p.id = r.matched_product_id "
               "LEFT JOIN external_catalog_sources s ON s.id = r.source_id WHERE 1=1")
        params: list = []
        if status:
            sql += " AND r.status = ?"
            params.append(status)
        sql += " ORDER BY r.created_at DESC, r.rowid DESC LIMIT ?"
        params.append(int(limit))
        return [{"id": r[0], "name": r[1], "brand": r[2], "barcode": r[3],
                 "category": r[4], "net_weight": r[5], "unit": r[6], "status": r[7],
                 "score": int(r[8] or 0), "matched_product_id": r[9],
                 "matched_label": f"{r[10]} · {r[11]}" if r[11] else "",
                 "source_name": r[12], "created_at": r[13]}
                for r in self._conn.execute(sql, params).fetchall()]
