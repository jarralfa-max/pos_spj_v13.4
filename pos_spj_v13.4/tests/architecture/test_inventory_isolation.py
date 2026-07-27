"""Architecture tests: Delivery must not read inventory directly."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
DELIVERY_UI = ROOT / "modulos" / "delivery.py"
DELIVERY_UC = ROOT / "core" / "delivery" / "application" / "change_delivery_status.py"


def test_delivery_ui_no_direct_inventory_sql():
    """delivery.py must not query inventory tables directly."""
    src = DELIVERY_UI.read_text(encoding="utf-8")
    for lineno, line in enumerate(src.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if re.search(
            r"productos\.existencia|inventario_sucursal|inventory_movements|inventario_actual",
            line,
            re.IGNORECASE,
        ):
            raise AssertionError(
                f"Direct inventory SQL in delivery UI line {lineno}:\n  {line.strip()}"
            )


def test_delivery_ui_no_commit():
    """delivery.py UI layer must never call commit/rollback."""
    src = DELIVERY_UI.read_text(encoding="utf-8")
    for lineno, line in enumerate(src.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if re.search(r"\.(commit|rollback)\s*\(", line):
            raise AssertionError(
                f"commit/rollback in delivery UI line {lineno}:\n  {line.strip()}"
            )


def test_change_status_uc_accepts_inventory_service():
    """ChangeDeliveryStatusUseCase must accept an inventory_service parameter."""
    src = DELIVERY_UC.read_text(encoding="utf-8")
    assert "inventory_service" in src, (
        "ChangeDeliveryStatusUseCase must accept an inventory_service parameter "
        "for stock availability checks at preparacion"
    )


def test_delivery_service_wires_inventory_balance_service():
    """delivery_service._change_status_use_case must pass inventory_service."""
    src = (ROOT / "core" / "services" / "delivery_service.py").read_text(encoding="utf-8")
    assert "InventoryBalanceService" in src, (
        "delivery_service.py must import and wire InventoryBalanceService "
        "into _change_status_use_case"
    )
