"""ConfigurationActivationPolicy — extra governance on top of
`ConfigurationValue.activate()`'s state-machine guard.

The entity itself already refuses to activate anything that isn't
APPROVED/SCHEDULED; this policy adds definition-aware rules the entity
can't know about: segregation of duties for `approval_required`
definitions (§59-60), and restart-required notices (§54).
"""

from __future__ import annotations

from backend.domain.settings.exceptions import ConfigurationActivationNotAllowedError


def assert_can_activate(definition, value, *, activator_user_id: str) -> None:
    if definition.approval_required and value.approved_by_user_id == activator_user_id:
        raise ConfigurationActivationNotAllowedError(
            "Quien aprobó este cambio de configuración crítica no puede activarlo también — "
            "se requiere un segundo usuario (segregación de funciones, §59-60)."
        )


def activation_requires_restart(definition) -> bool:
    return bool(definition.restart_required)
