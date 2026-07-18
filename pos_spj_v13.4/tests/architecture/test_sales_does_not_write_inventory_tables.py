"""INV-11 (§23, §64) — Sales/POS never writes canonical inventory tables directly.

The POS consults availability (query) and confirms sales (events); the stock
effect is owned by the inventory context via SALE_ISSUE/SALE_RETURN movements.
No sales module may INSERT/UPDATE/DELETE a canonical inventory table.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SALES_SOURCES = [
    REPO / "modulos" / "ventas.py",
    REPO / "core" / "services" / "sales_service.py",
    REPO / "core" / "services" / "sales",
    REPO / "core" / "use_cases" / "venta.py",
    REPO / "application" / "use_cases" / "venta.py",
]

_CANONICAL_TABLES = (
    "inventory_ledger", "inventory_ledger_lines", "inventory_balances",
    "inventory_reservation", "inventory_allocation", "inventory_lots",
    "inventory_operation_limits", "inventory_temperature_readings",
    "inventory_temperature_excursions",
)
_WRITE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+[\"'`]?(" + "|".join(_CANONICAL_TABLES) + r")\b",
    re.IGNORECASE)


def _files():
    for src in SALES_SOURCES:
        if src.is_file():
            yield src
        elif src.is_dir():
            for p in src.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_sales_does_not_write_canonical_inventory_tables():
    offenders = []
    for path in _files():
        for m in _WRITE.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)}")
    assert not offenders, (
        "Ventas/POS escribe tablas de inventario canónicas directamente "
        "(debe usar disponibilidad + eventos SALE_ISSUE/SALE_RETURN):\n"
        + "\n".join(offenders))
