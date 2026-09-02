"""IntegrationInstance — SET-19 "Instances"/"Credentials": one configured
instance of an `IntegrationDefinition` for this business (e.g. "our
WhatsApp Business number"). `config` holds non-secret settings (a phone
number id, a webhook path, ...); `credential_references` maps a required
credential name to a `SecretStoreGateway` secret name — never a raw
secret value.

§19: "Los secretos o credenciales no deben guardarse dentro de
connection_parameters. Usar referencia segura." — enforced here exactly
like `backend.domain.device_management.value_objects.connection_profile.
ConnectionProfile` already enforces it for hardware connections
(independently reimplemented, not imported — bounded-context
independence): `config` is scanned for secret-looking keys and rejected
outright.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.integrations.exceptions import IntegrationsInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7

_SECRET_LIKE_SUBSTRINGS = (
    "password", "secret", "token", "credential", "apikey", "api_key",
    "privatekey", "private_key", "auth",
)


def _assert_no_secret_like_keys(config: dict) -> None:
    offenders = [
        key for key in config
        if any(marker in key.strip().lower().replace(" ", "") for marker in _SECRET_LIKE_SUBSTRINGS)
    ]
    if offenders:
        raise IntegrationsInvalidValueError(
            f"config no puede contener claves con apariencia de secreto: {offenders}. "
            "Usa credential_references (SecretStoreGateway) en su lugar."
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class IntegrationInstance:
    id: str
    definition_id: str
    name: str
    config: dict = field(default_factory=dict)
    credential_references: dict = field(default_factory=dict)
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, definition_id: str, name: str, config: dict | None = None,
        credential_references: dict | None = None,
    ) -> "IntegrationInstance":
        if not name.strip():
            raise IntegrationsInvalidValueError("name es obligatorio")
        config = dict(config or {})
        _assert_no_secret_like_keys(config)
        return cls(
            id=new_uuid(), definition_id=validate_uuidv7(definition_id), name=name.strip(), config=config,
            credential_references=dict(credential_references or {}),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_details(self, *, name: str, config: dict | None = None) -> None:
        if not name.strip():
            raise IntegrationsInvalidValueError("name es obligatorio")
        config = dict(config or {})
        _assert_no_secret_like_keys(config)
        self.name = name.strip()
        self.config = config
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def set_credential_reference(self, credential_name: str, secret_name: str) -> None:
        self.credential_references[credential_name] = secret_name
        self._touch()
