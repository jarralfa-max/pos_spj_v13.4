"""CRM-1 (§37, "Todo importe usa Decimal") — customer_credit is Decimal-only.

No ``float`` type annotations/coercions in backend/domain/customer_credit or
backend/application/customer_credit, and no ``REAL`` columns for credit
amounts in the CRM schema once it exists. AST-based like
``test_inventory_uses_decimal.py`` / ``test_pricing_uses_money_decimal.py``,
so a docstring that merely mentions "float" does not trigger it.
"""

from __future__ import annotations

import ast
import re

from .customers_crm_guardrails import crm_py_files, existing_crm_schema_files, relative

_CREDIT_COLUMN_HINT = re.compile(
    r"^\s*\w*(credit_limit|credit_balance|current_exposure|available_credit|monto)\w*\s+REAL\b",
    re.IGNORECASE,
)


def _credit_py_files():
    from .customers_crm_guardrails import REPO

    roots = [
        REPO / "backend" / "domain" / "customer_credit",
        REPO / "backend" / "application" / "customer_credit",
        REPO / "backend" / "infrastructure" / "db" / "repositories" / "customer_credit",
    ]
    return crm_py_files(roots)


def _is_float_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "float"


def test_no_float_usage_in_customer_credit_code():
    offenders = []
    for path in _credit_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_float_name(node.func):
                offenders.append(f"{relative(path)}:{node.lineno}: float() call")
            if isinstance(node, ast.AnnAssign) and _is_float_name(node.annotation):
                offenders.append(f"{relative(path)}:{node.lineno}: float annotation")
            if isinstance(node, ast.arg) and node.annotation is not None and _is_float_name(node.annotation):
                offenders.append(f"{relative(path)}:{node.lineno}: float arg")
            if isinstance(node, ast.FunctionDef) and node.returns is not None and _is_float_name(node.returns):
                offenders.append(f"{relative(path)}:{node.lineno}: -> float")
    assert not offenders, "float usage in customer_credit (usar Decimal):\n" + "\n".join(offenders)


def test_no_real_columns_for_credit_amounts_in_crm_schema():
    offenders = []
    for schema_file in existing_crm_schema_files():
        for line in schema_file.read_text(encoding="utf-8").splitlines():
            if _CREDIT_COLUMN_HINT.search(line):
                offenders.append(f"{relative(schema_file)}: {line.strip()}")
    assert not offenders, "columnas REAL para montos de crédito (usar TEXT decimal):\n" + "\n".join(offenders)
