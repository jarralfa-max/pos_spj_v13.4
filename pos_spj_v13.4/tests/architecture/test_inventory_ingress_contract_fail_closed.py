"""P1-A guardrail (§5/§5.4) — los handlers de ingreso al ledger canónico de
Inventario resuelven el sobre fail-closed.

Los handlers que postean al ledger canónico (Ventas/Compras/Producción) NO deben:

- caer `warehouse_id = ... or branch_id` (un almacén no es una sucursal), ni
- fabricar el actor con `... or "system"`.

Deben delegar en `resolve_ingress` (o, cuando no llevan almacén, aplicar un guard
fail-closed del actor). Los *bridges* legacy que escriben tablas legacy
(`lotes`/`movimientos_lote`) quedan fuera de este contrato y se retiran en P2.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_HANDLERS = _ROOT / "backend/application/event_handlers/inventory"

# Handlers que postean al ledger canónico y deben cumplir el contrato fail-closed.
_CANONICAL_HANDLERS = (
    "customer_return_handler.py",
    "purchase_receipt_handler.py",
    "supplier_return_handler.py",
    "goods_receipt_reversed_handler.py",
    "production_execution_handler.py",
)

_WAREHOUSE_EQ_BRANCH = re.compile(r"or\s+branch_id\b")
_SYSTEM_ACTOR = re.compile(r"""or\s+["']system["']""")


def _offending_lines(path: Path, pattern: re.Pattern) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        code = line.split("#", 1)[0]  # ignora comentarios
        if pattern.search(code):
            out.append(code.strip())
    return out


def test_canonical_ledger_handlers_never_default_warehouse_to_branch():
    offenders: list[str] = []
    for name in _CANONICAL_HANDLERS:
        for line in _offending_lines(_HANDLERS / name, _WAREHOUSE_EQ_BRANCH):
            offenders.append(f"{name}: {line}")
    assert offenders == [], (
        "warehouse_id = ... or branch_id en handler canónico (§5):\n"
        + "\n".join(offenders))


def test_canonical_ledger_handlers_never_fabricate_system_actor():
    offenders: list[str] = []
    for name in _CANONICAL_HANDLERS:
        for line in _offending_lines(_HANDLERS / name, _SYSTEM_ACTOR):
            offenders.append(f"{name}: {line}")
    assert offenders == [], (
        'actor = ... or "system" en handler canónico (§5.4):\n'
        + "\n".join(offenders))


def test_canonical_ledger_handlers_use_the_shared_ingress_contract():
    """Los handlers con sobre completo (almacén/sucursal/actor) usan
    ``resolve_ingress``; ``goods_receipt_reversed`` no lleva almacén y aplica su
    propio guard fail-closed del actor."""
    without_warehouse = {"goods_receipt_reversed_handler.py"}
    missing: list[str] = []
    for name in _CANONICAL_HANDLERS:
        if name in without_warehouse:
            continue
        src = (_HANDLERS / name).read_text(encoding="utf-8")
        if "resolve_ingress" not in src:
            missing.append(name)
    assert missing == [], (
        "Handler canónico sin usar resolve_ingress:\n" + "\n".join(missing))
