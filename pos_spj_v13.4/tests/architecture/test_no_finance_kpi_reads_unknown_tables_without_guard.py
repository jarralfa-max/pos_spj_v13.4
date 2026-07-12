"""KPIs de Finanzas: toda lectura verifica existencia de tabla antes de consultar.

FinanceReadRepository no puede romper el dashboard porque falte una tabla
opcional, ni leer tablas vacías como fuente principal cuando existe la fuente
canónica (ventas, compras, cierres_caja, CxC/CxP, journal_entries).
"""

from __future__ import annotations

import ast
import re

from .architecture_guardrails import APP_ROOT

REPO_PATH = (
    APP_ROOT
    / "backend"
    / "infrastructure"
    / "db"
    / "repositories"
    / "finance_read_repository.py"
)

FROM_TABLE_RE = re.compile(r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)

# Métodos infra que reciben la tabla ya validada por el caller.
EXEMPT_METHODS = {"_scalar", "_rows", "_table_exists"}


def test_finance_kpi_reads_are_guarded() -> None:
    source = REPO_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name in EXEMPT_METHODS:
            continue
        method_src = ast.get_source_segment(source, node) or ""
        tables = set(FROM_TABLE_RE.findall(method_src)) - {"sqlite_master"}
        if not tables:
            continue
        guarded = "_table_exists" in method_src or 'table="' in method_src
        if not guarded:
            offenders.append(f"{node.name} → {sorted(tables)}")

    assert not offenders, (
        "Métodos de FinanceReadRepository leyendo tablas sin guard de existencia:\n"
        + "\n".join(offenders)
    )


def test_finance_kpis_use_canonical_sales_filter() -> None:
    """sum_sales filtra por estado (cancelada/anulada), no por columnas fantasma."""
    source = REPO_PATH.read_text(encoding="utf-8")
    assert "COALESCE(anulado,0)" not in source, (
        "ventas no tiene columna `anulado` — usar estado NOT IN ('cancelada','anulada')"
    )
