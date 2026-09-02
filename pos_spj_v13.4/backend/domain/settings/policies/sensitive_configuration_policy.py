"""SensitiveConfigurationPolicy — masking and access-gating for
`ConfigurationDefinition.sensitive` values (§46, §63: "Los secretos deben
aparecer enmascarados en `before` y `after`").

This module never touches raw secrets — `SECRET_REFERENCE` values are
already just a lookup name into `SecretStoreGateway`
(`backend/security/secrets/`), never the secret itself. `sensitive=True`
also covers non-secret settings a definition author wants masked in the
UI/audit trail (e.g. a financial threshold), independent of `value_type`.
"""

from __future__ import annotations

from backend.domain.settings.exceptions import SensitiveConfigurationAccessDeniedError

_MASK = "••••••"


def assert_can_view_raw(definition, *, has_sensitive_access: bool) -> None:
    if definition.sensitive and not has_sensitive_access:
        raise SensitiveConfigurationAccessDeniedError(
            f"{definition.key}: se requiere el permiso de configuración sensible "
            "para ver el valor sin enmascarar."
        )


def mask_for_display(definition, value: object) -> object:
    """Return `value` unchanged for non-sensitive definitions, or a
    display-safe mask otherwise. Never returns enough of the original
    value to reconstruct it."""
    if not definition.sensitive or value is None:
        return value
    return _MASK
