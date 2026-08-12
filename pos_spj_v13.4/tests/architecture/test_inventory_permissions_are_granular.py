"""INV-1 (§46, §64) — the inventory context uses granular permissions only.

Every sensitive inventory action is gated by its own granular `INVENTARIO.accion`
permission (the app-wide canonical `MODULO.accion` format, see
`core/security/permission_catalog.py`), validated in the backend; a single
broad "INVENTARIO.ver" gating every action must never exist.
"""

from __future__ import annotations

from pathlib import Path

from backend.application.inventory.permissions import (
    ALL_INVENTORY_PERMISSIONS,
    InventoryPermissions,
)

REPO = Path(__file__).resolve().parents[2]


def test_inventory_permissions_are_granular():
    assert len(ALL_INVENTORY_PERMISSIONS) >= 60
    # representative sample of the granular vocabulary
    for code in (
        InventoryPermissions.MOVEMENT_REVERSE,
        InventoryPermissions.COUNT_CONFIRM,
        InventoryPermissions.COUNT_VIEW_EXPECTED,
        InventoryPermissions.ADJUSTMENT_APPROVE,
        InventoryPermissions.QUALITY_RELEASE,
        InventoryPermissions.WEIGHT_MANUAL_OVERRIDE,
        InventoryPermissions.NEGATIVE_OVERRIDE,
        InventoryPermissions.RECEIPT_REVERSE,
        InventoryPermissions.DISPOSAL_AUTHORIZE,
    ):
        assert code in ALL_INVENTORY_PERMISSIONS


def test_every_permission_is_inventario_prefixed_string():
    for code in ALL_INVENTORY_PERMISSIONS:
        assert isinstance(code, str) and code.startswith("INVENTARIO.")
