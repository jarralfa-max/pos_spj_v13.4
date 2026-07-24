"""PRC-8 guardrail — no NUEVO código lee las tablas de precio legacy.

El motor de precio canónico (Pricing/Costing) reemplaza `listas_precio` /
`precios_lista` / `precios_volumen` / `clientes_lista_precio` / `historial_precios`.
Tras reescribir `core/services/pricing_service.py` como shim delegante, ningún
archivo de aplicación debe consultar esas tablas por SQL.

Ratchet: la allowlist enumera los lectores legacy que aún quedan (se eliminan en el
corte de Productos, PROD-19). La lista sólo puede **decrecer**; agregar un archivo
nuevo que lea estas tablas rompe el test.

Se escanean literales SQL (AST) en el código de aplicación — no `migrations/`
(definen/backfillean el esquema), ni `tools/`, ni `tests/`, ni docstrings.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = ("backend", "core", "modulos", "frontend", "integrations", "services")
_LEGACY_TABLES = (
    "listas_precio", "precios_lista", "precios_volumen",
    "clientes_lista_precio", "historial_precios",
)

# Lectores legacy tolerados hoy (se eliminan en PROD-19 / corte final).
# Rutas relativas a la raíz del proyecto. La lista SÓLO puede reducirse.
_ALLOWLIST = {
    "backend/infrastructure/db/repositories/branch_product_repository.py",
}


def _sql_literals(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            up = node.value.upper()
            if any(k in up for k in ("SELECT ", " FROM ", "UPDATE ", "INSERT ", "JOIN ")):
                out.append(node.value.lower())
    return out


def _reads_legacy(sql: str) -> bool:
    for table in _LEGACY_TABLES:
        for token in (f" {table} ", f" {table}\n", f" {table}(", f".{table} ", f" {table}$"):
            if token.rstrip("$") in sql + " ":
                return True
    return False


def test_no_new_legacy_pricing_reads():
    offenders: list[str] = []
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = str(path.relative_to(_ROOT))
            if rel in _ALLOWLIST:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(_reads_legacy(sql) for sql in _sql_literals(tree)):
                offenders.append(rel)
    assert not offenders, (
        "Código nuevo lee tablas de precio legacy (usa el contexto canónico "
        "Pricing/Costing):\n" + "\n".join(sorted(offenders)))
