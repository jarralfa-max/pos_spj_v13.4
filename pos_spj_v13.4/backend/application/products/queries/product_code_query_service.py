"""PreviewProductCodeQueryService + generación (P0-04).

`preview` muestra el código que se asignaría (sin consumir la secuencia). El uso de
`reserve_next` (consumir) lo hace el alta del producto dentro de su transacción, de
modo que la reserva se liga a una creación exitosa (sin huecos ante rollback).
"""

from __future__ import annotations

from backend.domain.products.policies.product_code_generation_policy import (
    format_code,
    resolve_rule,
)
from backend.infrastructure.db.repositories.products.code_sequence_repository import (
    ProductCodeSequenceRepository,
)


class PreviewProductCodeQueryService:
    def __init__(self, connection) -> None:
        self._repo = ProductCodeSequenceRepository(connection)

    def preview(self, *, product_type: str, category_id: str | None = None) -> str:
        rules = self._repo.load_rules()
        rule = resolve_rule(rules, product_type=product_type, category_id=category_id)
        return format_code(rule, self._repo.peek(rule.prefix))


def reserve_next_code(connection, *, product_type: str,
                      category_id: str | None = None) -> str:
    """Consume el consecutivo y devuelve el código. El caller controla la
    transacción (no hace commit aquí)."""
    repo = ProductCodeSequenceRepository(connection)
    rule = resolve_rule(repo.load_rules(), product_type=product_type,
                        category_id=category_id)
    seq = repo.reserve(rule.prefix, padding=rule.padding)
    return format_code(rule, seq)
