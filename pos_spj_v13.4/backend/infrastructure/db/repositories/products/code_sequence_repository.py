"""ProductCodeSequenceRepository (P0-04) — reglas + consecutivos por prefijo.

`peek` calcula el próximo código sin consumir (para la vista previa); `reserve`
consume el consecutivo de forma transaccional (INSERT-or-UPDATE atómico) y devuelve
el valor. El caller es dueño de la transacción (reserva ligada a la creación del
producto → sin huecos si la creación falla y se hace rollback). Offline.
"""

from __future__ import annotations

from backend.domain.products.policies.product_code_generation_policy import CodeRule


class ProductCodeSequenceRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def load_rules(self) -> dict[tuple[str, str], CodeRule]:
        rows = self._conn.execute(
            "SELECT scope_type, scope_value, prefix, padding, separator "
            "FROM product_code_generation_rules WHERE active=1").fetchall()
        return {(r["scope_type"], r["scope_value"] or ""):
                CodeRule(prefix=r["prefix"], padding=int(r["padding"]),
                         separator=r["separator"]) for r in rows}

    def peek(self, prefix: str) -> int:
        row = self._conn.execute(
            "SELECT next_value FROM product_code_sequences WHERE prefix=?",
            (prefix,)).fetchone()
        return int(row["next_value"]) if row else 1

    def reserve(self, prefix: str, *, padding: int = 6) -> int:
        """Consume y devuelve el próximo consecutivo del prefijo (atómico)."""
        row = self._conn.execute(
            "SELECT next_value FROM product_code_sequences WHERE prefix=?",
            (prefix,)).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO product_code_sequences (prefix, next_value, padding) "
                "VALUES (?, 2, ?)", (prefix, padding))
            return 1
        current = int(row["next_value"])
        self._conn.execute(
            "UPDATE product_code_sequences SET next_value=next_value+1, "
            "updated_at=datetime('now') WHERE prefix=?", (prefix,))
        return current
