"""Product code generation policy (P0-04) — pura: prefijo + formato.

Dada la resolución de reglas (categoría > tipo de producto > default), produce el
prefijo y formatea ``PREFIJO-000001``. No toca persistencia ni secuencias; el
repositorio reserva el consecutivo. Offline por diseño.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodeRule:
    prefix: str
    padding: int = 6
    separator: str = "-"


def resolve_rule(rules_by_scope: dict[tuple[str, str], CodeRule], *,
                 product_type: str, category_id: str | None) -> CodeRule:
    """Precedencia: CATEGORY(category_id) > PRODUCT_TYPE(type) > DEFAULT."""
    if category_id and ("CATEGORY", category_id) in rules_by_scope:
        return rules_by_scope[("CATEGORY", category_id)]
    if ("PRODUCT_TYPE", product_type) in rules_by_scope:
        return rules_by_scope[("PRODUCT_TYPE", product_type)]
    if ("DEFAULT", "") in rules_by_scope:
        return rules_by_scope[("DEFAULT", "")]
    return CodeRule(prefix="PRD")


def format_code(rule: CodeRule, sequence: int) -> str:
    return f"{rule.prefix}{rule.separator}{sequence:0{rule.padding}d}"
