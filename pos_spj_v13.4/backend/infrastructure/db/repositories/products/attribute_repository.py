"""ProductAttributeRepository (P1-03) — atributos + opciones enumeradas.

Escritura parametrizada, sin commit (el caso de uso es dueño de la transacción).
"""

from __future__ import annotations

from backend.domain.products.entities.product_attribute import (
    AttributeDataType,
    AttributeOption,
    ProductAttribute,
)


def _row_to_attribute(row) -> ProductAttribute:
    return ProductAttribute(id=row["id"], code=row["code"], name=row["name"],
                            data_type=AttributeDataType(row["data_type"]),
                            active=bool(row["active"]))


def _row_to_option(row) -> AttributeOption:
    return AttributeOption(id=row["id"], attribute_id=row["attribute_id"],
                           code=row["code"], label=row["label"],
                           sort_order=int(row["sort_order"]), active=bool(row["active"]))


class ProductAttributeRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── atributos ──────────────────────────────────────────────────────────
    def get(self, attribute_id: str) -> ProductAttribute | None:
        row = self._conn.execute(
            "SELECT * FROM product_attributes WHERE id=?", (attribute_id,)).fetchone()
        return _row_to_attribute(row) if row is not None else None

    def code_exists(self, code: str, *, exclude_id: str | None = None) -> bool:
        sql = "SELECT 1 FROM product_attributes WHERE code=?"
        params: list = [(code or "").strip().upper()]
        if exclude_id:
            sql += " AND id<>?"
            params.append(exclude_id)
        return self._conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    def list_all(self, *, active_only: bool = False) -> list[ProductAttribute]:
        sql = "SELECT * FROM product_attributes"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY name"
        return [_row_to_attribute(r) for r in self._conn.execute(sql).fetchall()]

    def create(self, attribute: ProductAttribute) -> None:
        self._conn.execute(
            "INSERT INTO product_attributes "
            "(id, code, name, name_normalized, data_type, active, created_by) "
            "VALUES (?,?,?,?,?,?,?)",
            (attribute.id, attribute.code, attribute.name, attribute.name_normalized,
             attribute.data_type.value, 1 if attribute.active else 0,
             getattr(attribute, "created_by", None)))

    def update_fields(self, attribute_id: str, *, code: str, name: str,
                      name_normalized: str) -> None:
        self._conn.execute(
            "UPDATE product_attributes SET code=?, name=?, name_normalized=?, "
            "updated_at=datetime('now') WHERE id=?",
            (code, name, name_normalized, attribute_id))

    def set_active(self, attribute_id: str, active: bool) -> None:
        self._conn.execute(
            "UPDATE product_attributes SET active=?, updated_at=datetime('now') "
            "WHERE id=?", (1 if active else 0, attribute_id))

    # ── opciones ───────────────────────────────────────────────────────────
    def get_option(self, option_id: str) -> AttributeOption | None:
        row = self._conn.execute(
            "SELECT * FROM product_attribute_options WHERE id=?",
            (option_id,)).fetchone()
        return _row_to_option(row) if row is not None else None

    def option_code_exists(self, attribute_id: str, code: str, *,
                           exclude_id: str | None = None) -> bool:
        sql = ("SELECT 1 FROM product_attribute_options "
               "WHERE attribute_id=? AND code=?")
        params: list = [attribute_id, (code or "").strip().upper()]
        if exclude_id:
            sql += " AND id<>?"
            params.append(exclude_id)
        return self._conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    def list_options(self, attribute_id: str, *, active_only: bool = False
                     ) -> list[AttributeOption]:
        sql = "SELECT * FROM product_attribute_options WHERE attribute_id=?"
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY sort_order, label"
        return [_row_to_option(r)
                for r in self._conn.execute(sql, (attribute_id,)).fetchall()]

    def add_option(self, option: AttributeOption) -> None:
        self._conn.execute(
            "INSERT INTO product_attribute_options "
            "(id, attribute_id, code, label, sort_order, active) "
            "VALUES (?,?,?,?,?,?)",
            (option.id, option.attribute_id, option.code, option.label,
             option.sort_order, 1 if option.active else 0))

    def update_option(self, option_id: str, *, code: str, label: str,
                      sort_order: int, active: bool) -> None:
        self._conn.execute(
            "UPDATE product_attribute_options SET code=?, label=?, sort_order=?, "
            "active=? WHERE id=?",
            (code, label, sort_order, 1 if active else 0, option_id))
