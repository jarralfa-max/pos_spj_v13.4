"""CredentialProvisioningPolicy — SET-19 "Credentials": whether an
`IntegrationInstance` actually has every credential its
`IntegrationDefinition` requires. Mirrors
`backend.domain.document_output.value_objects.label_variable_set.
LabelVariableSet.assert_satisfied()`'s "catch it before it's used, not
when the external API call fails" discipline (SET-14).
"""

from __future__ import annotations

from backend.domain.integrations.entities.integration_definition import IntegrationDefinition
from backend.domain.integrations.entities.integration_instance import IntegrationInstance
from backend.domain.integrations.exceptions import MissingCredentialError


def assert_credentials_satisfied(definition: IntegrationDefinition, instance: IntegrationInstance) -> None:
    missing = [
        name for name in definition.required_credential_names
        if not instance.credential_references.get(name)
    ]
    if missing:
        raise MissingCredentialError(
            f"La instancia {instance.name!r} de {definition.code!r} no tiene referencia de credencial "
            f"para: {missing}"
        )
