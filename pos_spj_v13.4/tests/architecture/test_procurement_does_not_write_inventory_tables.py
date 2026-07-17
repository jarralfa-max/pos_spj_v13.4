"""PUR-13.10 — procurement never writes inventory tables directly.

Only the accepted quantity of a GoodsReceipt enters stock, and it does so through
an event (INVENTORY_ADJUSTMENT_REGISTERED) consumed by the Inventory context.
The canonical procurement code must not UPDATE/INSERT inventory tables nor call
legacy stock mutators.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROCUREMENT_ROOTS = [
    REPO / "backend" / "domain" / "procurement",
    REPO / "backend" / "application" / "procurement",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "procurement",
    REPO / "frontend" / "desktop" / "modules" / "purchasing",
]

_FORBIDDEN = re.compile(
    r"UPDATE\s+productos\s+SET\s+existencia"
    r"|UPDATE\s+inventario"
    r"|INSERT\s+INTO\s+inventario"
    r"|INSERT\s+INTO\s+existencias"
    r"|actualizar_stock\s*\("
    r"|sumar_inventario\s*\("
    r"|registrar_entrada_compra\s*\("
    r"|actualizar_inventario_compra\s*\(",
    re.IGNORECASE,
)


def _files():
    for root in PROCUREMENT_ROOTS:
        if root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_procurement_does_not_write_inventory_tables():
    offenders = []
    for path in _files():
        for m in _FORBIDDEN.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)!r}")
    assert not offenders, (
        "Compras no afecta inventario directamente; usa el evento de recepción "
        "(cantidad aceptada) hacia el contexto de Inventario:\n" + "\n".join(offenders))
