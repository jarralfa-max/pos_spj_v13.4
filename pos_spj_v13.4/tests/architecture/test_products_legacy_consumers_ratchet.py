"""PROD-19 paso 9 (prep) — ratchet de consumidores legacy de `productos`.

Congela el conjunto de archivos que aún leen/escriben la tabla legacy `productos`
por SQL directo. Mientras el corte de Productos avanza, este guardrail impide
**agregar nuevos** consumidores legacy: la allowlist sólo puede **decrecer**. El
objetivo del paso 10 es allowlist **vacía** → entonces el DROP de `productos` es
seguro.

Escanea literales SQL (AST) en el código de aplicación (no migraciones/tests/docs).
Cuando un archivo se repunta al maestro canónico `products` (o a
`ProductCatalogService`/`PricingReadFacade`/`inventory_balances`), se elimina de la
allowlist; si vuelve a aparecer, el test falla.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = ("backend", "core", "modulos", "frontend", "integrations", "services",
              "repositories", "application", "interfaz", "sync")
_FROM_PRODUCTOS = re.compile(r"\b(from|into|update|join)\s+productos\b", re.IGNORECASE)


def _sql_literals(tree: ast.AST) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            up = node.value.upper()
            if any(k in up for k in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ",
                                     "JOIN ", " FROM ")):
                out.append(node.value)
    return out


def _current_consumers() -> set[str]:
    hits: set[str] = set()
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            if any(_FROM_PRODUCTOS.search(sql) for sql in _sql_literals(tree)):
                hits.add(path.relative_to(_ROOT).as_posix())
    return hits


# Allowlist congelada (PROD-19 paso 9). SÓLO puede reducirse: repuntar un archivo al
# maestro canónico y borrarlo de aquí. Objetivo del paso 10: conjunto vacío.
# PROD-22 (2026-10-09): VACÍA. El borrado de `core/`/`modulos/` se llevó 35 de
# las 42 entradas; las 7 restantes eran código sin llamadores (borrado) o un
# docstring. La migración 325 retira la tabla `productos`: cualquier lectura
# nueva fallaría en producción, y este test la detiene antes.
_ALLOWLIST: frozenset[str] = frozenset()


def test_no_new_legacy_productos_consumers():
    current = _current_consumers()
    new = current - _ALLOWLIST
    assert not new, (
        "Nuevos consumidores de la tabla legacy `productos` (repunta a `products` "
        "canónico / ProductCatalogService / PricingReadFacade / inventory_balances):\n"
        + "\n".join(sorted(new)))


def test_allowlist_has_no_stale_entries():
    """La allowlist no debe listar archivos que ya NO leen `productos` (mantiene el
    ratchet honesto: al repuntar un archivo, se borra de la allowlist)."""
    current = _current_consumers()
    stale = _ALLOWLIST - current
    assert not stale, ("Entradas obsoletas en la allowlist (bórralas, ya no leen "
                       "`productos`):\n" + "\n".join(sorted(stale)))
