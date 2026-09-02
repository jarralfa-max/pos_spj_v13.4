"""AuthorizationGrant — the audit record of a Configuración hot
authorization (SET-1, §48/§59 discipline reused from
`backend.domain.inventory.value_objects.authorization_grant`).

A hot authorization is a second, distinct user signing off on an action
the requester cannot approve alone (e.g. approving a document template
version someone else drafted). This is the immutable domain record the
use cases/presenter build; persistence lands in
`ConfiguracionAuthorizationLogRepository`.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.settings.exceptions import ConfigurationInvalidValueError


@dataclass(frozen=True)
class AuthorizationGrant:
    permission_code: str
    requested_by: str
    authorized_by: str
    operation_id: str
    reason: str
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not self.permission_code:
            raise ConfigurationInvalidValueError("permission_code requerido")
        if not self.requested_by:
            raise ConfigurationInvalidValueError("requested_by requerido")
        if not self.authorized_by:
            raise ConfigurationInvalidValueError("authorized_by requerido")
        if not self.operation_id:
            raise ConfigurationInvalidValueError("operation_id requerido")
        if not (self.reason or "").strip():
            raise ConfigurationInvalidValueError("La autorización requiere un motivo")
