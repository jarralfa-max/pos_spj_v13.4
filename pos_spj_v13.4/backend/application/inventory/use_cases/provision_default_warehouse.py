"""ProvisionDefaultWarehouseUseCase (§P0-E prerequisite) — a real default
warehouse per branch, with technical locations.

CLAUDE.md forbids ``warehouse_id = branch_id`` / ``location_id = warehouse_id``,
but the Sales/Production/Purchase bridges do exactly that today because no
branch has ever had a warehouse: the ``warehouses`` table is seeded by no
migration, script, or bootstrap step, and the Almacenes UI has no create
action yet (§7.4 audit finding). Repointing those bridges to resolve a real
warehouse before one exists anywhere would break every sale, production run
and purchase receipt immediately — the opposite of PRIORIDAD 0 ("no perder
lógica de negocio").

This use case is the prerequisite: idempotently ensure a branch has one
CENTRAL warehouse (all allocation flags on, since it must serve sales,
purchases, production and quarantine alike) with its technical locations
(RECEIVING/AVAILABLE/PICKING/QUARANTINE/DAMAGED/TRANSIT/RETURNS/PRODUCTION)
seeded. Only once every branch has this can the bridges (a separate, later
change) resolve a real warehouse/location instead of substituting the branch.
"""

from __future__ import annotations

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.use_cases.ensure_technical_locations import (
    EnsureTechnicalLocationsUseCase,
)
from backend.application.inventory.use_cases.warehouse_use_cases import (
    CreateWarehouseUseCase,
)
from backend.domain.inventory.enums import WarehouseType


def default_warehouse_code(branch_id: str) -> str:
    """Deterministic per-branch code — the idempotency key CreateWarehouseUseCase
    already checks (unique by code), so calling this use case repeatedly for the
    same branch never creates a duplicate warehouse."""
    return f"WH-DEFAULT-{branch_id}"


class ProvisionDefaultWarehouseUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._create_warehouse = CreateWarehouseUseCase(authorization)
        self._ensure_locations = EnsureTechnicalLocationsUseCase()

    def execute(self, connection, *, branch_id: str, actor_user_id: str,
                branch_name: str = "") -> InventoryResult:
        branch = str(branch_id or "").strip()
        if not branch:
            return InventoryResult.fail("Sucursal requerida", "BRANCH_REQUIRED")
        code = default_warehouse_code(branch)
        result = self._create_warehouse.execute(
            connection, code=code,
            name=f"Almacén principal — {branch_name or branch}",
            branch_id=branch, warehouse_type=WarehouseType.CENTRAL,
            actor_user_id=actor_user_id,
            allow_sales_allocation=True, allow_purchase_receipt=True,
            allow_production=True, allow_quarantine=True)
        if not result.success:
            return result
        warehouse_id = result.entity_id
        already_existed = bool(result.data.get("idempotent"))
        locations = self._ensure_locations.execute(connection, warehouse_id=warehouse_id)
        return InventoryResult.ok(
            "Almacén principal ya existía (idempotente)" if already_existed
            else "Almacén principal creado",
            entity_id=warehouse_id, warehouse_id=warehouse_id,
            already_existed=already_existed, locations=locations)
