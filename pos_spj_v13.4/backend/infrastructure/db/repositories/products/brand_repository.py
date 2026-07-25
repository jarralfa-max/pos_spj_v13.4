"""ProductBrandRepository (P1-02) — persistencia del catálogo plano de marcas.

Escritura parametrizada, sin commit (el caso de uso es dueño de la transacción).
"""

from __future__ import annotations

from backend.domain.products.entities.brand import Brand


def _row_to_entity(row) -> Brand:
    return Brand(id=row["id"], code=row["code"], name=row["name"],
                 description=row["description"], active=bool(row["active"]))


class ProductBrandRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def get(self, brand_id: str) -> Brand | None:
        row = self._conn.execute(
            "SELECT * FROM product_brands WHERE id=?", (brand_id,)).fetchone()
        return _row_to_entity(row) if row is not None else None

    def code_exists(self, code: str, *, exclude_id: str | None = None) -> bool:
        sql = "SELECT 1 FROM product_brands WHERE code=?"
        params: list = [(code or "").strip().upper()]
        if exclude_id:
            sql += " AND id<>?"
            params.append(exclude_id)
        return self._conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    def list_all(self, *, active_only: bool = False) -> list[Brand]:
        sql = "SELECT * FROM product_brands"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY name"
        return [_row_to_entity(r) for r in self._conn.execute(sql).fetchall()]

    def create(self, brand: Brand) -> None:
        self._conn.execute(
            "INSERT INTO product_brands "
            "(id, code, name, name_normalized, description, active, created_by) "
            "VALUES (?,?,?,?,?,?,?)",
            (brand.id, brand.code, brand.name, brand.name_normalized,
             brand.description, 1 if brand.active else 0,
             getattr(brand, "created_by", None)))

    def update_fields(self, brand_id: str, *, code: str, name: str,
                      name_normalized: str, description: str | None) -> None:
        self._conn.execute(
            "UPDATE product_brands SET code=?, name=?, name_normalized=?, "
            "description=?, updated_at=datetime('now') WHERE id=?",
            (code, name, name_normalized, description, brand_id))

    def set_active(self, brand_id: str, active: bool) -> None:
        self._conn.execute(
            "UPDATE product_brands SET active=?, updated_at=datetime('now') "
            "WHERE id=?", (1 if active else 0, brand_id))
