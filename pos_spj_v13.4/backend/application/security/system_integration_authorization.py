"""Autorización REAL para llamadas entre contextos (integraciones de sistema).

EL PROBLEMA
-----------
Los adaptadores de producción construían `PostInventoryMovementUseCase()`,
`RegisterInventoryLotUseCase()` y `RegisterTraceabilityLinkUseCase()` sin
política, y esos casos de uso caían en `permissive_for_tests()`: en tiempo de
ejecución, cualquier llamada entre contextos pasaba sin revisar nada.

EL MODELO
---------
Cuando un operador ejecuta algo en un contexto (p. ej. Procesamiento) y ese
contexto pide a otro (Inventario) que mueva existencia, la petición sale en
nombre de ESE operador y de ESE módulo origen. El contexto DUEÑO declara qué
permisos concede a cada módulo origen (`IntegrationGrant`): un conjunto
cerrado, no "todo". Este verificador responde sí sólo cuando

- quien pide es exactamente el operador delegado (no otro usuario),
- el permiso está en el conjunto concedido a ese módulo origen.

El alcance (sucursal / almacén) lo valida el propio caso de uso destino con su
contexto de ejecución, que el adaptador construye con la sucursal y el almacén
de la orden. Cada decisión queda registrada (`decisions`) y en el log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("spj.security.system_integration")


@dataclass(frozen=True)
class IntegrationGrant:
    """Lo que el contexto DUEÑO permite pedir a un módulo origen."""

    owner_context: str
    source_module: str
    permissions: frozenset[str]

    def __post_init__(self) -> None:
        if not self.owner_context or not self.source_module:
            raise ValueError("La concesión necesita contexto dueño y módulo origen")
        if not self.permissions:
            raise ValueError("Una concesión vacía no concede nada; no la declares")


@dataclass(frozen=True)
class IntegrationDecision:
    owner_context: str
    source_module: str
    actor_user_id: str
    requested_by: str
    permission_code: str
    granted: bool
    decided_at: str


@dataclass
class DelegatedIntegrationPermissionChecker:
    """`PermissionChecker` para una llamada entre contextos en nombre de un
    operador autenticado. Nunca concede a un usuario distinto del delegado."""

    grant: IntegrationGrant
    actor_user_id: str
    decisions: list[IntegrationDecision] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.actor_user_id:
            raise ValueError("La integración necesita un operador autenticado")

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        concedido = (bool(user_id) and user_id == self.actor_user_id
                     and permission_code in self.grant.permissions)
        decision = IntegrationDecision(
            owner_context=self.grant.owner_context, source_module=self.grant.source_module,
            actor_user_id=self.actor_user_id, requested_by=str(user_id or ""),
            permission_code=permission_code, granted=concedido,
            decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.decisions.append(decision)
        (logger.info if concedido else logger.warning)(
            "integración %s→%s: %s pide %s → %s", self.grant.source_module,
            self.grant.owner_context, user_id, permission_code,
            "concedido" if concedido else "DENEGADO")
        return concedido
