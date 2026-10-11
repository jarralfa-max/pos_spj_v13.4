"""ProductApprovalQueryService (PROD-22, §22/§39) — versiones técnicas pendientes.

Recetas, rendimientos, esquemas de despiece y combos se versionan y siguen el
ciclo BORRADOR → EN REVISIÓN → APROBADA → ACTIVA. Hasta ahora sólo se podían ver
y aprobar abriendo cada producto: quien aprueba no tenía dónde ver qué está
esperando su firma, y los KPI «Recetas sin aprobar» y «Rendimientos pendientes»
del Resumen no llevaban a ningún lado. Read-only, una consulta por tipo.
"""

from __future__ import annotations

PENDING_STATUSES = ("DRAFT", "UNDER_REVIEW", "APPROVED")

#: tipo → (tabla de versiones, FK al padre, tabla padre, columna de producto,
#:         ¿la versión guarda created_by?)
_KINDS = {
    "RECIPE": ("recipe_versions", "recipe_id", "recipes", "product_id", True),
    "YIELD": ("yield_profile_versions", "yield_profile_id", "yield_profiles",
              "input_product_id", True),
    "CUTTING": ("cutting_scheme_versions", "cutting_scheme_id", "cutting_schemes",
                "input_product_id", False),
    "BUNDLE": ("bundle_versions", "bundle_id", "product_bundles", "product_id", False),
}


class ProductApprovalQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def pending(self, *, kind: str | None = None, status: str | None = None) -> list[dict]:
        rows: list[dict] = []
        placeholders = ",".join("?" for _ in PENDING_STATUSES)
        has_users = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone()
        for key, (versions, fk, parent, product_col, has_creator) in _KINDS.items():
            if kind and kind != key:
                continue
            creator = "v.created_by" if has_creator else "NULL"
            user_name = (f"COALESCE(u.nombre, u.usuario, {creator})" if has_users
                         else creator)
            user_join = f"LEFT JOIN usuarios u ON u.id = {creator} " if has_users else ""
            sql = (f"SELECT v.id, v.version_number, v.status, v.created_at, {creator}, "
                   f"h.name, p.id, p.code, p.name, {user_name} "
                   f"FROM {versions} v JOIN {parent} h ON h.id = v.{fk} "
                   f"LEFT JOIN products p ON p.id = h.{product_col} {user_join}"
                   f"WHERE v.status IN ({placeholders})")
            params: list = list(PENDING_STATUSES)
            if status:
                sql += " AND v.status = ?"
                params.append(status)
            for r in self._conn.execute(sql, params).fetchall():
                rows.append({"kind": key, "version_id": r[0], "version_number": r[1],
                             "status": r[2], "created_at": r[3], "created_by": r[4],
                             "name": r[5], "product_id": r[6], "product_code": r[7],
                             "product_name": r[8], "created_by_name": r[9]})
        order = {"UNDER_REVIEW": 0, "APPROVED": 1, "DRAFT": 2}
        rows.sort(key=lambda r: (order.get(r["status"], 9), r["created_at"] or ""))
        return rows

    def counts(self) -> dict[str, int]:
        result = {s: 0 for s in PENDING_STATUSES}
        for row in self.pending():
            result[row["status"]] += 1
        return result
