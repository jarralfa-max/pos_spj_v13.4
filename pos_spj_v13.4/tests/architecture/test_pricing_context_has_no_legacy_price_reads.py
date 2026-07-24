"""PRC-6 guardrail — el contexto canónico de Pricing/Costing no lee tablas legacy.

Pricing es la fuente de verdad de precio/costo: su código (domain/application/
infrastructure) sólo consulta las tablas born-clean (``product_price``,
``product_cost``, ``price_list``, ``volume_price``, ``customer_price_list``). No
debe leer el precio/costo desde el legacy (``productos``, ``precios_lista``,
``precios_volumen``, ``listas_precio``, ``inventario_actual``, ``historial_precios``);
ese acoplamiento es justo lo que el contexto elimina.

La migración de backfill (150) sí toca el legacy — vive en ``migrations/`` y no se
escanea aquí. El repunte de los 44 consumidores legacy se valida en PRC-8.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = (
    _ROOT / "backend" / "domain" / "pricing",
    _ROOT / "backend" / "application" / "pricing",
    _ROOT / "backend" / "infrastructure" / "db" / "repositories" / "pricing",
)
_LEGACY_TABLES = (
    "productos", "precios_lista", "precios_volumen", "listas_precio",
    "clientes_lista_precio", "inventario_actual", "historial_precios",
    "branch_products",
)


def _sql_string_literals(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.upper()
            if any(kw in s for kw in ("SELECT ", " FROM ", "UPDATE ", "INSERT ", "JOIN ")):
                out.append(node.value)
    return out


def test_pricing_context_reads_no_legacy_price_tables():
    offenders: list[str] = []
    for base in _SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for sql in _sql_string_literals(tree):
                low = sql.lower()
                for table in _LEGACY_TABLES:
                    # límite de palabra tosco: la tabla rodeada por no-identificadores
                    for token in (f" {table} ", f" {table}(", f" {table}\n",
                                  f"{table} ", f".{table} "):
                        if token in low + " ":
                            offenders.append(f"{path.relative_to(_ROOT)}: '{table}' en SQL")
                            break
    assert not offenders, "Pricing lee tablas legacy de precio/costo:\n" + "\n".join(offenders)
