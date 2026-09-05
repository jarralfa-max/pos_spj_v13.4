"""ASSET-1 (§55, §110) — Activos never decrements inventory stock directly.

Refacciones usadas en mantenimiento fluyen via WorkOrder -> PartsRequest ->
Inventory (reservation/consumption owned by Inventario). Activos must never
call inventory stock-mutation entry points directly.
"""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import ALL_ASSET_CODE_ROOTS, asset_py_files, relative

_FORBIDDEN = re.compile(
    r"\bdescontar_stock\b"
    r"|\bconsumir_stock\b"
    r"|InventoryRepository\b"
    r"|inventory_movements\b"
    r"|\bStockMovement\b",
)


def test_assets_do_not_write_inventory_stock():
    offenders = []
    for path in asset_py_files(ALL_ASSET_CODE_ROOTS):
        text = path.read_text(encoding="utf-8")
        for m in _FORBIDDEN.finditer(text):
            offenders.append(f"{relative(path)}: {m.group(0)!r}")
    assert not offenders, (
        "Activos escribe/descuenta inventario directamente (debe usar "
        "PartsRequest -> Inventory):\n" + "\n".join(offenders)
    )
