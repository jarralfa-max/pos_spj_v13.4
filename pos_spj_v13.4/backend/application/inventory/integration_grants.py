"""Qué puede pedir cada módulo origen a Inventario (concesiones de integración).

Inventario es el DUEÑO: aquí, y sólo aquí, se declara qué permisos de
Inventario ejerce otro contexto cuando actúa en nombre de su operador. Todo lo
que no está en la lista se deniega. Ver
`backend/application/security/system_integration_authorization.py`.
"""

from __future__ import annotations

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions as P
from backend.application.security.system_integration_authorization import (
    DelegatedIntegrationPermissionChecker,
    IntegrationGrant,
)

#: Procesamiento reserva insumos, los consume, recibe salidas en un lote de
#: producción y enlaza la genealogía. No libera ni bloquea calidad.
MEAT_PROCESSING_GRANT = IntegrationGrant(
    owner_context="inventory", source_module="meat_processing",
    permissions=frozenset({P.RESERVATION_CREATE, P.RESERVATION_RELEASE, P.MOVEMENT_CREATE,
                           P.LOT_CREATE, P.TRACEABILITY_LINK}))

#: Calidad decide sobre lo que está en cuarentena: libera o bloquea el lote y
#: mueve su existencia entre estados de calidad.
QUALITY_GRANT = IntegrationGrant(
    owner_context="inventory", source_module="quality",
    permissions=frozenset({P.QUARANTINE_RELEASE, P.QUALITY_RELEASE, P.QUALITY_BLOCK,
                           P.LOT_RELEASE, P.LOT_BLOCK, P.MOVEMENT_CREATE}))

GRANTS = {g.source_module: g for g in (MEAT_PROCESSING_GRANT, QUALITY_GRANT)}


def inventory_policy_for(source_module: str, actor_user_id: str
                         ) -> tuple[InventoryAuthorizationPolicy,
                                    DelegatedIntegrationPermissionChecker]:
    grant = GRANTS.get(source_module)
    if grant is None:
        raise PermissionError(f"Inventario no concede nada al módulo «{source_module}»")
    checker = DelegatedIntegrationPermissionChecker(grant=grant, actor_user_id=actor_user_id)
    return InventoryAuthorizationPolicy(checker), checker


def inventory_scope_for(*, actor_user_id: str, branch_id: str,
                        warehouse_id: str) -> InventoryExecutionContext:
    """Alcance acotado a la sucursal y el almacén del documento origen: la
    integración no puede tocar otro almacén aunque el operador lo tenga."""
    return InventoryExecutionContext(
        actor_user_id=actor_user_id, active_branch_id=branch_id,
        assigned_branch_ids=frozenset({branch_id}),
        allowed_warehouse_ids=frozenset({warehouse_id}))
