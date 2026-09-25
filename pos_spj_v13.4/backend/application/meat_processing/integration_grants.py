"""Qué puede pedir cada módulo origen a Procesamiento Cárnico.

Calidad registra en el output la decisión que TOMÓ (y ya aplicó en Inventario).
No puede ejecutar, capturar ni cerrar nada en Procesamiento.
"""

from __future__ import annotations

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.permissions import MeatProcessingPermissions as P
from backend.application.security.system_integration_authorization import (
    DelegatedIntegrationPermissionChecker,
    IntegrationGrant,
)

QUALITY_CALLBACK_GRANT = IntegrationGrant(
    owner_context="meat_processing", source_module="quality",
    permissions=frozenset({P.QUALITY_RECORD_DECISION}))

_GRANTS = {QUALITY_CALLBACK_GRANT.source_module: QUALITY_CALLBACK_GRANT}


def meat_processing_policy_for(source_module: str,
                               actor_user_id: str) -> MeatProcessingAuthorizationPolicy:
    grant = _GRANTS.get(source_module)
    if grant is None:
        raise PermissionError(f"Procesamiento no concede nada al módulo «{source_module}»")
    return MeatProcessingAuthorizationPolicy(
        DelegatedIntegrationPermissionChecker(grant=grant, actor_user_id=actor_user_id))
