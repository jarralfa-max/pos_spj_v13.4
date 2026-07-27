"""ProductImageRepository (P1 imágenes) — galería por producto.

Escritura parametrizada, sin commit (el caso de uso es dueño de la transacción). El
invariante "exactamente una principal" lo coordina el caso de uso llamando a
``clear_primary`` antes de marcar la nueva.
"""

from __future__ import annotations

from backend.domain.products.entities.product_image import ProductImage


def _row_to_entity(row) -> ProductImage:
    return ProductImage(id=row["id"], product_id=row["product_id"], uri=row["uri"],
                        alt_text=row["alt_text"], is_primary=bool(row["is_primary"]),
                        sort_order=int(row["sort_order"]))


class ProductImageRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def get(self, image_id: str) -> ProductImage | None:
        row = self._conn.execute(
            "SELECT * FROM product_images WHERE id=?", (image_id,)).fetchone()
        return _row_to_entity(row) if row is not None else None

    def list_for_product(self, product_id: str) -> list[ProductImage]:
        rows = self._conn.execute(
            "SELECT * FROM product_images WHERE product_id=? "
            "ORDER BY is_primary DESC, sort_order, created_at", (product_id,)).fetchall()
        return [_row_to_entity(r) for r in rows]

    def count_for_product(self, product_id: str) -> int:
        return int(self._conn.execute(
            "SELECT COUNT(*) AS n FROM product_images WHERE product_id=?",
            (product_id,)).fetchone()["n"])

    def add(self, image: ProductImage) -> None:
        self._conn.execute(
            "INSERT INTO product_images "
            "(id, product_id, uri, alt_text, is_primary, sort_order, created_by) "
            "VALUES (?,?,?,?,?,?,?)",
            (image.id, image.product_id, image.uri, image.alt_text,
             1 if image.is_primary else 0, image.sort_order,
             getattr(image, "created_by", None)))

    def clear_primary(self, product_id: str) -> None:
        self._conn.execute(
            "UPDATE product_images SET is_primary=0 WHERE product_id=?", (product_id,))

    def set_primary(self, image_id: str) -> None:
        self._conn.execute(
            "UPDATE product_images SET is_primary=1 WHERE id=?", (image_id,))

    def remove(self, image_id: str) -> None:
        self._conn.execute("DELETE FROM product_images WHERE id=?", (image_id,))

    def first_other(self, product_id: str, *, exclude_id: str) -> ProductImage | None:
        row = self._conn.execute(
            "SELECT * FROM product_images WHERE product_id=? AND id<>? "
            "ORDER BY sort_order, created_at LIMIT 1",
            (product_id, exclude_id)).fetchone()
        return _row_to_entity(row) if row is not None else None
