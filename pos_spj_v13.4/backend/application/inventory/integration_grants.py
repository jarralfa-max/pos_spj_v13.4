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

#: Transferencias reserva en el origen, despacha (salida) y recibe (entrada) en
#: el destino. No crea lotes: la mercancía viaja con los lotes que ya tenía.
TRANSFERS_GRANT = IntegrationGrant(
    owner_context="inventory", source_module="transfers",
    permissions=frozenset({P.RESERVATION_CREATE, P.RESERVATION_RELEASE, P.MOVEMENT_CREATE}))

#: Auditoría de permisos 968e0bc (PER-02). Hasta aquí estos cuatro módulos
#: movían existencia con `PostInventoryMovementUseCase()` SIN política, que caía
#: en `permissive_for_tests()`: cualquier llamada pasaba sin revisar nada. Ahora
#: el caso de uso sin política falla cerrada y cada uno pide sólo lo suyo.

#: Ventas: la salida por venta y el reingreso por devolución/cancelación. La
#: venta en sí ya la autorizó Ventas; el cajero NO necesita el permiso genérico
#: de movimiento manual para que su venta descuente existencia.
SALES_GRANT = IntegrationGrant(
    owner_context="inventory", source_module="sales",
    permissions=frozenset({P.MOVEMENT_CREATE}))

#: Compras: la entrada por recepción (con su lote), la devolución a proveedor y
#: el reverso de una recepción.
PROCUREMENT_GRANT = IntegrationGrant(
    owner_context="inventory", source_module="procurement",
    permissions=frozenset({P.MOVEMENT_CREATE, P.LOT_CREATE, P.MOVEMENT_REVERSE}))

#: Fidelidad: la salida del producto que se entrega como recompensa.
LOYALTY_GRANT = IntegrationGrant(
    owner_context="inventory", source_module="loyalty",
    permissions=frozenset({P.MOVEMENT_CREATE}))

#: Pedidos: aparta y libera la mercancía de un pedido; no la mueve.
ORDERS_DELIVERY_GRANT = IntegrationGrant(
    owner_context="inventory", source_module="orders_delivery",
    permissions=frozenset({P.RESERVATION_CREATE, P.RESERVATION_RELEASE}))

GRANTS = {g.source_module: g for g in (
    MEAT_PROCESSING_GRANT, QUALITY_GRANT, TRANSFERS_GRANT, SALES_GRANT, PROCUREMENT_GRANT,
    LOYALTY_GRANT, ORDERS_DELIVERY_GRANT)}


class _NoActorChecker:
    """Un evento sin operador no concede nada (§5.4: nunca se inventa
    «system»). Deniega en vez de reventar, como antes."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


def inventory_policy_for(source_module: str, actor_user_id: str
                         ) -> tuple[InventoryAuthorizationPolicy,
                                    DelegatedIntegrationPermissionChecker]:
    grant = GRANTS.get(source_module)
    if grant is None:
        raise PermissionError(f"Inventario no concede nada al módulo «{source_module}»")
    checker = DelegatedIntegrationPermissionChecker(grant=grant, actor_user_id=actor_user_id)
    return InventoryAuthorizationPolicy(checker), checker


def inventory_integration_policy(source_module: str,
                                 actor_user_id: str) -> InventoryAuthorizationPolicy:
    """La política con la que un módulo origen llama a un caso de uso de
    Inventario en nombre de su operador. Sin operador, deniega."""
    if not str(actor_user_id or "").strip():
        if source_module not in GRANTS:
            raise PermissionError(f"Inventario no concede nada al módulo «{source_module}»")
        return InventoryAuthorizationPolicy(_NoActorChecker())
    return inventory_policy_for(source_module, str(actor_user_id))[0]


def integration_use_case(use_case_cls, source_module: str, actor_user_id: str):
    """`use_case_cls` construido con la concesión de `source_module`."""
    return use_case_cls(inventory_integration_policy(source_module, actor_user_id))


def inventory_scope_for(*, actor_user_id: str, branch_id: str,
                        warehouse_id: str) -> InventoryExecutionContext:
    """Alcance acotado a la sucursal y el almacén del documento origen: la
    integración no puede tocar otro almacén aunque el operador lo tenga."""
    return InventoryExecutionContext(
        actor_user_id=actor_user_id, active_branch_id=branch_id,
        assigned_branch_ids=frozenset({branch_id}),
        allowed_warehouse_ids=frozenset({warehouse_id}))
