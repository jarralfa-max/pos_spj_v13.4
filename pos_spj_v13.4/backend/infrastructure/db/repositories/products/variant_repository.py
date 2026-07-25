"""ProductVariantRepository (P1-03) — hijos-variante y sus asignaciones de atributo.

Escritura parametrizada, sin commit (el caso de uso es dueño de la transacción). Las
asignaciones (product_id, attribute_id → option_id) definen la combinación de cada
variante; la firma de combinación permite evitar duplicados al regenerar.
"""

from __future__ import annotations


class ProductVariantRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def record_assignment(self, *, assignment_id: str, product_id: str,
                          attribute_id: str, option_id: str | None,
                          value_text: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO product_variant_assignments "
            "(id, product_id, attribute_id, option_id, value_text) "
            "VALUES (?,?,?,?,?)",
            (assignment_id, product_id, attribute_id, option_id, value_text))

    def list_variants(self, parent_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, code, name, lifecycle_status FROM products "
            "WHERE parent_product_id=? ORDER BY code", (parent_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_assignments(self, product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT attribute_id, option_id, value_text "
            "FROM product_variant_assignments WHERE product_id=?",
            (product_id,)).fetchall()
        return [dict(r) for r in rows]

    def existing_combos(self, parent_id: str) -> set[frozenset[tuple[str, str]]]:
        """Firmas de combinación (por opción) de las variantes ya existentes."""
        rows = self._conn.execute(
            "SELECT a.product_id, a.attribute_id, a.option_id "
            "FROM product_variant_assignments a "
            "JOIN products p ON p.id = a.product_id "
            "WHERE p.parent_product_id=?", (parent_id,)).fetchall()
        by_product: dict[str, set[tuple[str, str]]] = {}
        for r in rows:
            if r["option_id"] is None:
                continue
            by_product.setdefault(r["product_id"], set()).add(
                (r["attribute_id"], r["option_id"]))
        return {frozenset(combo) for combo in by_product.values()}
