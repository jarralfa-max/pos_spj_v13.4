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
        draft = c.execute(
            "SELECT COUNT(*) FROM products WHERE lifecycle_status='DRAFT'").fetchone()[0]
        under_review = c.execute(
            "SELECT COUNT(*) FROM products "
            "WHERE lifecycle_status='UNDER_REVIEW'").fetchone()[0]
        return {"active": active, "meat": meat, "internal": internal,
                "incomplete": incomplete, "recipes_unapproved": recipes_unapproved,
                "yield_pending": yield_pending, "draft": draft,
                "under_review": under_review}

    def list_catalog(self, *, query: str | None = None, product_type: str | None = None,
                     limit: int = 200) -> list[dict]:
        """Listado del catálogo maestro, por el contrato compartido de búsqueda.

        Tenía SQL propio con su PROPIA semántica de coincidencia
        (`name_normalized LIKE minúsculas` / `code LIKE mayúsculas`), que es
        justo lo que hacía que el mismo texto diera resultados distintos según
        la pantalla. Ahora coincide igual que todos: nombre normalizado, nombre,
        código y código de barras.

        `active_only=False` es deliberado: esta tabla existe precisamente para
        ver borradores y productos en revisión. Y conserva la forma de fila que
        `catalog_table` pinta, incluidos estado y si es cárnico.
        """
        from backend.application.products.queries.product_selection_query_service import (
            ProductCatalogSearchQueryService,
            ProductSearchQuery,
        )
        dtos = ProductCatalogSearchQueryService(self._conn).search(ProductSearchQuery(
            text=(query or "").strip() or None, product_type=product_type,
            active_only=False, page_size=int(limit)))
        return [{"id": d.product_id, "code": d.code, "name": d.name,
                 "product_type": d.product_type,
                 "lifecycle_status": d.lifecycle_status,
                 "is_meat": d.product_type in _MEAT_VALUES} for d in dtos]

    def list_recent_alerts(self, *, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT entity_id, severity, alert_type, message FROM product_notification_log "
            "WHERE status='SENT' ORDER BY created_at DESC LIMIT ?", (int(limit),)).fetchall()
        return [{"entity_id": r["entity_id"], "severity": r["severity"],
                 "alert_type": r["alert_type"], "message": r["message"]} for r in rows]
