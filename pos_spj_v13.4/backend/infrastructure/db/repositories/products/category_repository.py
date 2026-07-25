"""ProductCategoryRepository (P1-01) — persistencia del árbol de categorías.

Escritura parametrizada, sin commit (el caso de uso es dueño de la transacción). Las
lecturas de subárbol usan la ruta materializada (``path LIKE '/id/%'``). Al mover una
rama se reescriben ``path``/``depth`` de todos los descendientes en la misma tx.
"""

from __future__ import annotations

from backend.domain.products.entities.product_category import ProductCategory


def _row_to_entity(row) -> ProductCategory:
    return ProductCategory(
        id=row["id"], code=row["code"], name=row["name"],
        parent_id=row["parent_id"], depth=int(row["depth"]), path=row["path"],
        sort_order=int(row["sort_order"]), active=bool(row["active"]))


class ProductCategoryRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── lectura ───────────────────────────────────────────────────────────
    def get(self, category_id: str) -> ProductCategory | None:
        row = self._conn.execute(
            "SELECT * FROM product_categories WHERE id=?", (category_id,)).fetchone()
        return _row_to_entity(row) if row is not None else None

    def code_exists(self, code: str, *, exclude_id: str | None = None) -> bool:
        sql = "SELECT 1 FROM product_categories WHERE code=?"
        params: list = [(code or "").strip().upper()]
        if exclude_id:
            sql += " AND id<>?"
            params.append(exclude_id)
        return self._conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    def list_all(self, *, active_only: bool = False) -> list[ProductCategory]:
        sql = "SELECT * FROM product_categories"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY depth, sort_order, name"
        return [_row_to_entity(r) for r in self._conn.execute(sql).fetchall()]

    def children(self, parent_id: str | None) -> list[ProductCategory]:
        if parent_id is None:
            rows = self._conn.execute(
                "SELECT * FROM product_categories WHERE parent_id IS NULL "
                "ORDER BY sort_order, name").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM product_categories WHERE parent_id=? "
                "ORDER BY sort_order, name", (parent_id,)).fetchall()
        return [_row_to_entity(r) for r in rows]

    def has_active_children(self, parent_id: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM product_categories WHERE parent_id=? AND active=1 LIMIT 1",
            (parent_id,)).fetchone() is not None

    def descendants(self, category: ProductCategory) -> list[ProductCategory]:
        """Descendientes (sin incluir la propia categoría), por su ruta materializada."""
        rows = self._conn.execute(
            "SELECT * FROM product_categories WHERE path LIKE ? AND id<>? "
            "ORDER BY depth, sort_order, name",
            (f"{category.path}%", category.id)).fetchall()
        return [_row_to_entity(r) for r in rows]

    # ── escritura (sin commit) ────────────────────────────────────────────
    def create(self, category: ProductCategory) -> None:
        self._conn.execute(
            "INSERT INTO product_categories "
            "(id, code, name, name_normalized, parent_id, path, depth, sort_order, "
            "active, created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (category.id, category.code, category.name, category.name_normalized,
             category.parent_id, category.path, category.depth, category.sort_order,
             1 if category.active else 0, getattr(category, "created_by", None)))

    def update_fields(self, category_id: str, *, code: str, name: str,
                      name_normalized: str, sort_order: int) -> None:
        self._conn.execute(
            "UPDATE product_categories SET code=?, name=?, name_normalized=?, "
            "sort_order=?, updated_at=datetime('now') WHERE id=?",
            (code, name, name_normalized, sort_order, category_id))

    def set_active(self, category_id: str, active: bool) -> None:
        self._conn.execute(
            "UPDATE product_categories SET active=?, updated_at=datetime('now') "
            "WHERE id=?", (1 if active else 0, category_id))

    def reparent(self, category_id: str, *, parent_id: str | None, path: str,
                 depth: int) -> None:
        self._conn.execute(
            "UPDATE product_categories SET parent_id=?, path=?, depth=?, "
            "updated_at=datetime('now') WHERE id=?",
            (parent_id, path, depth, category_id))

    def rewrite_subtree(self, *, old_prefix: str, new_prefix: str,
                        depth_delta: int) -> None:
        """Reescribe path/depth de los descendientes tras mover una rama (misma tx)."""
        rows = self._conn.execute(
            "SELECT id, path, depth FROM product_categories WHERE path LIKE ? "
            "AND path<>?", (f"{old_prefix}%", old_prefix)).fetchall()
        for r in rows:
            new_path = new_prefix + r["path"][len(old_prefix):]
            self._conn.execute(
                "UPDATE product_categories SET path=?, depth=? WHERE id=?",
                (new_path, int(r["depth"]) + depth_delta, r["id"]))
