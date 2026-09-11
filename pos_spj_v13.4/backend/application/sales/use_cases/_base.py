"""Shared plumbing for Sales/POS use cases — authorization injection and
outbox event emission. Mirrors
backend/application/customers/use_cases/lifecycle_use_cases.py::_BaseUseCase
(`_emit`) shape, adapted to Sales' outbox repository signature.

Sales' UnitOfWork has no `.audit` repository (SALES-2 deliberately reuses
the generic `core.services.auto_audit.audit_write` sink instead, which needs
a `container`, not a bare `connection` — see backend/application/sales/audit.py's
own docstring). These use cases therefore only enqueue to `sales_outbox`
(real, atomic, backed by SALES-4's schema) — they do NOT call
`record_sales_audit_entry`, since that would require threading a `container`
through every use case in addition to `connection`, a real API-shape
decision deferred to whichever future phase wires these use cases into the
real UI (which already has a `container` on hand). Documented as an open gap
in docs/refactor/SALES-6_application_layer.md, not silently skipped.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.domain.sales.events import sale_event_payload

#: Identidad de las operaciones sin persona detrás (barridos programados).
#: Mismo criterio que ya usan `cash_register_application_service` y
#: `execute_meat_production_use_case` al quedarse sin usuario.
SYSTEM_ACTOR = "sistema"


class _SalesBaseUseCase:
    """Fontanería común: autorización y emisión de eventos al outbox.

    `inventory_authorization` es la política con la que Ventas habla con
    Inventario. Se inyecta desde el mismo sitio que la de Ventas (la raíz de
    composición del POS) en vez de construirse aquí: un adaptador que se fabrica
    su propio permiso no es un permiso.
    """

    def __init__(
        self, authorization: SalesAuthorizationPolicy | None = None,
        inventory_authorization: InventoryAuthorizationPolicy | None = None,
        customer_authorization: CustomerAuthorizationPolicy | None = None,
    ) -> None:
        self._auth = authorization or SalesAuthorizationPolicy()
        self._inventory_auth = inventory_authorization
        self._customer_auth = customer_authorization

    def _inventory_client(self, connection, *, branch_id: str, actor_user_id: str):
        """Cliente de inventario con la identidad y el permiso del llamador.

        Sin `inventory_authorization` inyectada, el cliente construye una
        política sin verificador, que lanza `InventoryConfigurationError` en
        cuanto se usa. Preferible a conceder de más, y sobre todo distinguible:
        un cableado incompleto no debe confundirse con una falta de permiso.
        """
        from backend.infrastructure.integrations.sales_inventory_client import (
            SalesInventoryClient,
        )

        return SalesInventoryClient(
            connection, branch_id=branch_id, actor_user_id=actor_user_id,
            authorization=self._inventory_auth)

    def _credit_client(self, connection, actor_user_id: str):
        """Cliente de crédito con la identidad y el permiso del llamador.

        Misma forma que `_inventory_client`: la política se inyecta desde la
        raíz de composición, y sin ella el cliente no concede nada.
        """
        from backend.infrastructure.integrations.sales_credit_client import SalesCreditClient

        return SalesCreditClient(connection, actor_user_id=actor_user_id,
                                 authorization=self._customer_auth)

    @staticmethod
    def _emit(uow, event_name: str, *, entity_id: str, operation_id: str,
              branch_id: str, actor_user_id: str, **extra) -> None:
        payload = sale_event_payload(
            event_name, operation_id=operation_id, entity_id=entity_id,
            branch_id=branch_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(
            event_id=payload["event_id"], event_name=event_name,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            operation_id=operation_id)
