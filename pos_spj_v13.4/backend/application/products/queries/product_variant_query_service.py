"""ProductVariantQueryService — read side de variantes (P1-03).

Lista las variantes (productos hijo) de un padre con su combinación de atributos
legible, para la pantalla de generación/gestión. Read-only.
"""

from __future__ import annotations


class ProductVariantQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_variants(self, parent_product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, code, name, lifecycle_status FROM products "
            "WHERE parent_product_id=? ORDER BY code", (parent_product_id,)).fetchall()
        variants = []
        for r in rows:
            variants.append({
                "id": r["id"], "code": r["code"], "name": r["name"],
                "lifecycle_status": r["lifecycle_status"],
                "attributes": self._attribute_values(r["id"]),
            })
        return variants

    def variant_count(self, parent_product_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM products WHERE parent_product_id=?",
            (parent_product_id,)).fetchone()
        return int(row["n"])

    def _attribute_values(self, product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT a.name AS attribute, o.label AS value "
            "FROM product_variant_assignments va "
            "JOIN product_attributes a ON a.id = va.attribute_id "
            "LEFT JOIN product_attribute_options o ON o.id = va.option_id "
            "WHERE va.product_id=? ORDER BY a.name", (product_id,)).fetchall()
        return [{"attribute": r["attribute"], "value": r["value"]} for r in rows]
