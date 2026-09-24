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
        """La sucursal PROPIA se permite siempre; los permisos sólo ENSANCHAN.

        CAMBIADO EL 2026-09-17 POR DECISIÓN DEL USUARIO, tras medir contra la
        base viva. Antes esto exigía un permiso POSITIVO y explícito
        (`VIEW_OWN_BRANCH`) incluso para la sucursal del propio usuario. Ese
        permiso no está concedido a NADIE: `rol_permisos` sólo tiene las 5
        acciones gruesas por módulo y los códigos de alcance suman CERO filas en
        los seis módulos que los declaran. La matriz de roles canónica tampoco
        lo otorga a ninguno de sus diez roles. Resultado real con los 4 usuarios
        de la instalación —`admin` incluido, sobre su PROPIA sucursal—:
        `BranchScopeError`.

        `admin` fallaba además por una segunda causa: `PermissionQueryService`
        devuelve `{"*"}` sin expandir y la comprobación de abajo es de
        pertenencia LITERAL, que no entiende comodines (a diferencia de
        `PermissionEvaluator`). Eso sigue afectando SÓLO al escape global
        `VIEW_ALL_BRANCHES`, no al acceso a la sucursal propia, y se dejó
        deliberadamente fuera de esta decisión.

        La regla de abajo es la de `LossExecutionContext.enforce_branch` y
        `MeatProcessingExecutionContext.enforce_branch`, copiada a propósito:
        eran dos interpretaciones incompatibles del MISMO vocabulario de tres
        niveles, dos de los tres módulos ya usaban ésta, y era la única viable
        contra datos reales.
        """
        target = str(target_branch_id or "").strip()
        if not target:
            raise BranchScopeError("La operación requiere una sucursal válida")
        if InventoryPermissions.VIEW_ALL_BRANCHES in set(user_permissions):
            return
        allowed = {str(user_branch_id or "").strip()}
        allowed.update(str(branch or "").strip() for branch in assigned_branch_ids)
        allowed.discard("")
        if target in allowed:
            return
        raise BranchScopeError(
            f"El usuario no tiene alcance sobre la sucursal {target}")

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
