"""IntegrationDefinition — SET-19 "Definitions": the catalog entry for
one *kind* of external system the ERP can integrate with (e.g. code
"WHATSAPP" category MESSAGING, code "MERCADOPAGO" category PAYMENTS —
the two integrations already real and live in this codebase, generalized
here rather than invented). `required_credential_names` lists which
named secrets an `IntegrationInstance` of this definition must provide
via `SecretStoreGateway` (§19 of the master prompt: "Los secretos...
Usar referencia segura") — never the secrets themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.integrations.enums import IntegrationCategory
from backend.domain.integrations.exceptions import IntegrationsInvalidValueError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class IntegrationDefinition:
    id: str
    code: str
    name: str
    category: IntegrationCategory
    required_credential_names: tuple[str, ...] = ()
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, code: str, name: str, category: IntegrationCategory,
        required_credential_names: tuple[str, ...] | list[str] = (),
    ) -> "IntegrationDefinition":
        if not code.strip():
            raise IntegrationsInvalidValueError("code es obligatorio")
        if not name.strip():
            raise IntegrationsInvalidValueError("name es obligatorio")
        names = tuple(required_credential_names)
        if len(names) != len(set(names)):
            raise IntegrationsInvalidValueError(
                f"required_credential_names no puede tener duplicados: {names}"
            )
        return cls(
            id=new_uuid(), code=code.strip().upper(), name=name.strip(), category=category,
            required_credential_names=names,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_details(
        self, *, name: str, required_credential_names: tuple[str, ...] | list[str] = (),
    ) -> None:
        if not name.strip():
            raise IntegrationsInvalidValueError("name es obligatorio")
        names = tuple(required_credential_names)
        if len(names) != len(set(names)):
            raise IntegrationsInvalidValueError(
                f"required_credential_names no puede tener duplicados: {names}"
            )
        self.name = name.strip()
        self.required_credential_names = names
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
