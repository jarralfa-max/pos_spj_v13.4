"""ProductImageQueryService — read side de la galería de imágenes (P1). Read-only."""

from __future__ import annotations


class ProductImageQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_images(self, product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, uri, alt_text, is_primary, sort_order FROM product_images "
            "WHERE product_id=? ORDER BY is_primary DESC, sort_order, created_at",
            (product_id,)).fetchall()
        return [{"id": r["id"], "uri": r["uri"], "alt_text": r["alt_text"],
                 "is_primary": bool(r["is_primary"]),
                 "sort_order": int(r["sort_order"])} for r in rows]

    def primary_image(self, product_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, uri, alt_text FROM product_images "
            "WHERE product_id=? AND is_primary=1 LIMIT 1", (product_id,)).fetchone()
        return dict(row) if row is not None else None
