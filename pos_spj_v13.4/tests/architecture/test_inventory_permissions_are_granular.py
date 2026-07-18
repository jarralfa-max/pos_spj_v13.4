"""INV-1 (§46, §64) — the inventory context uses granular permissions only.

Every sensitive inventory action is gated by an INVENTORY_* granular permission
validated in the backend; a single broad "INVENTORY_ALL" must never exist.
"""

from __future__ import annotations

from pathlib import Path

from backend.application.inventory.permissions import (
    ALL_INVENTORY_PERMISSIONS,
    InventoryPermissions,
)

REPO = Path(__file__).resolve().parents[2]


def test_inventory_permissions_are_granular():
    assert "INVENTORY_ALL" not in ALL_INVENTORY_PERMISSIONS
    assert len(ALL_INVENTORY_PERMISSIONS) >= 60
    # representative sample of the granular vocabulary
    for code in (
        InventoryPermissions.MOVEMENT_REVERSE,
        InventoryPermissions.TRANSFER_APPROVE,
        InventoryPermissions.TRANSFER_DISPATCH,
        InventoryPermissions.TRANSFER_RECEIVE,
        InventoryPermissions.COUNT_CONFIRM,
        InventoryPermissions.COUNT_VIEW_EXPECTED,
        InventoryPermissions.ADJUSTMENT_APPROVE,
        InventoryPermissions.QUALITY_RELEASE,
        InventoryPermissions.WEIGHT_MANUAL_OVERRIDE,
        InventoryPermissions.NEGATIVE_OVERRIDE,
    ):
        assert code in ALL_INVENTORY_PERMISSIONS


def test_every_permission_is_inventory_prefixed_string():
    for code in ALL_INVENTORY_PERMISSIONS:
        assert isinstance(code, str) and code.startswith("INVENTORY_")
