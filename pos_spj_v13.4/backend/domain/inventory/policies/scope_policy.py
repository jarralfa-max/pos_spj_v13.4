"""InventoryScopePolicy — branch and warehouse access scope (§45, §46).

Pure domain logic. The view-scope permission a user holds decides which branches
they may operate on; assigned-warehouse sets decide warehouse reach. The backend
enforces this on every use case — a user must never touch another branch's stock
just because the UI happened to show it.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.application.inventory.permissions import InventoryPermissions
from backend.domain.inventory.exceptions import BranchScopeError, WarehouseScopeError


class InventoryScopePolicy:
    def enforce_branch_access(
        self,
        *,
        user_permissions: Iterable[str],
        user_branch_id: str,
        assigned_branch_ids: Iterable[str],
        target_branch_id: str,
    ) -> None:
        perms = set(user_permissions)
        if InventoryPermissions.VIEW_ALL_BRANCHES in perms:
            return
        if (
            InventoryPermissions.VIEW_ASSIGNED_BRANCHES in perms
            and target_branch_id in set(assigned_branch_ids)
        ):
            return
        if (
            InventoryPermissions.VIEW_OWN_BRANCH in perms
            and target_branch_id
            and target_branch_id == user_branch_id
        ):
            return
        raise BranchScopeError(
            f"El usuario no tiene alcance sobre la sucursal {target_branch_id}")

    def enforce_warehouse_access(
        self,
        *,
        allowed_warehouse_ids: Iterable[str],
        target_warehouse_id: str,
        has_all_warehouses: bool = False,
    ) -> None:
        if has_all_warehouses:
            return
        if target_warehouse_id in set(allowed_warehouse_ids):
            return
        raise WarehouseScopeError(
            f"El usuario no tiene alcance sobre el almacén {target_warehouse_id}")
