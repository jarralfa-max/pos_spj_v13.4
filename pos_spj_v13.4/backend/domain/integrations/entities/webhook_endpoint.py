"""WebhookEndpoint — SET-19 "Webhooks": one registered inbound webhook
belonging to an `IntegrationInstance`. Generalizes the two real, live
webhook routes already in this codebase (`whatsapp_service/webhook/
whatsapp.py`'s Meta webhook, `whatsapp_service/webhook/mercadopago.py`'s
MercadoPago webhook, both signature-verified since SET-1/§14) into a
catalog entry — this bounded context never receives or dispatches actual
webhook traffic itself, only tracks what exists and its last-received
timestamp for observability.

`signing_secret_reference` is a `SecretStoreGateway` secret name (never a
raw secret), same "reference not value" discipline as
`IntegrationInstance.credential_references`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.integrations.enums import WebhookSignatureScheme
from backend.domain.integrations.exceptions import IntegrationsInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class WebhookEndpoint:
    id: str
    instance_id: str
    code: str
    path: str
    signature_scheme: WebhookSignatureScheme = WebhookSignatureScheme.NONE
    signing_secret_reference: str | None = None
    active: bool = True
    last_received_at: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, instance_id: str, code: str, path: str,
        signature_scheme: WebhookSignatureScheme = WebhookSignatureScheme.NONE,
        signing_secret_reference: str | None = None,
    ) -> "WebhookEndpoint":
        if not code.strip():
            raise IntegrationsInvalidValueError("code es obligatorio")
        if not path.strip().startswith("/"):
            raise IntegrationsInvalidValueError(f"path debe iniciar con '/', recibido {path!r}")
        if signature_scheme is not WebhookSignatureScheme.NONE and not signing_secret_reference:
            raise IntegrationsInvalidValueError(
                f"signature_scheme={signature_scheme.value} requiere signing_secret_reference"
            )
        return cls(
            id=new_uuid(), instance_id=validate_uuidv7(instance_id), code=code.strip().upper(),
            path=path.strip(), signature_scheme=signature_scheme,
            signing_secret_reference=signing_secret_reference,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def mark_received(self, *, at: datetime | None = None) -> None:
        self.last_received_at = (at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        self._touch()
