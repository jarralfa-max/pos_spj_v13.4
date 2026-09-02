"""resolve_mercadopago_secret_name — SET-19 cutover: `_get_token()`'s
real, previously-hardcoded credential resolution moved onto the
Integrations catalog (`IntegrationDefinition`/`IntegrationInstance`)
SET-19's own domain built with zero callers.

Designed conservatively — this touches live payment credential
resolution, the highest-risk surface this refactor track has cut over.
The bootstrapped default `credential_references` points at the EXACT
SAME secret name (`PaymentProviderSettingsService.SECRET_NAME`) already
in use, so an already-configured MercadoPago token is found immediately
on first use — no re-entry, no behavior change — until an admin
deliberately repoints the reference via the real Configuración
"Integraciones" UI. Any failure anywhere in this resolution (bootstrap,
lookup, missing reference) falls back to that same hardcoded constant,
never raises — `services/mercado_pago_service.py::_get_token()` must
degrade exactly as it always has, never block a real payment link.
"""

from __future__ import annotations

import logging

from backend.domain.integrations.entities.integration_definition import IntegrationDefinition
from backend.domain.integrations.entities.integration_instance import IntegrationInstance
from backend.domain.integrations.enums import IntegrationCategory
from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
    SqliteIntegrationDefinitionRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
    SqliteIntegrationInstanceRepository,
)

logger = logging.getLogger(__name__)

_DEFINITION_CODE = "MERCADOPAGO"
_CREDENTIAL_NAME = "mp_access_token"


def resolve_mercadopago_secret_name(connection) -> str:
    from core.services.configuration_settings_service import PaymentProviderSettingsService

    fallback = PaymentProviderSettingsService.SECRET_NAME
    try:
        definitions = SqliteIntegrationDefinitionRepository(connection)
        instances = SqliteIntegrationInstanceRepository(connection)

        definition = definitions.get_by_code(_DEFINITION_CODE)
        if definition is None:
            definition = IntegrationDefinition.create(
                code=_DEFINITION_CODE, name="MercadoPago", category=IntegrationCategory.PAYMENTS,
                required_credential_names=(_CREDENTIAL_NAME,),
            )
            definitions.save(definition)
            connection.commit()

        existing = instances.list_by_definition(definition.id)
        instance = existing[0] if existing else None
        if instance is None:
            instance = IntegrationInstance.create(
                definition_id=definition.id, name="MercadoPago",
                credential_references={_CREDENTIAL_NAME: fallback},
            )
            instances.save(instance)
            connection.commit()

        return instance.credential_references.get(_CREDENTIAL_NAME) or fallback
    except Exception:
        logger.exception("No se pudo resolver la referencia de credencial de MercadoPago; usando el nombre legacy")
        return fallback
