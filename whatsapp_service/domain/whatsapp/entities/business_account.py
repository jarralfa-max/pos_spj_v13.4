# domain/whatsapp/entities/business_account.py — WA-2 (prompt maestro §10)
"""WhatsAppBusinessAccount y WhatsAppProviderConfiguration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import AccountStatus, WhatsAppProvider


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WhatsAppBusinessAccount:
    id: str
    provider: WhatsAppProvider
    business_account_external_id: str
    display_name: str
    status: AccountStatus
    secret_reference_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        provider: WhatsAppProvider,
        business_account_external_id: str,
        display_name: str,
        secret_reference_id: Optional[str] = None,
    ) -> "WhatsAppBusinessAccount":
        if not business_account_external_id or not business_account_external_id.strip():
            raise ValueError("business_account_external_id es obligatorio")
        if not display_name or not display_name.strip():
            raise ValueError("display_name es obligatorio")
        now = _utcnow()
        return cls(
            id=new_id(),
            provider=provider,
            business_account_external_id=business_account_external_id.strip(),
            display_name=display_name.strip(),
            status=AccountStatus.DRAFT,
            secret_reference_id=secret_reference_id,
            created_at=now,
            updated_at=now,
        )

    def activate(self) -> None:
        if self.status == AccountStatus.RETIRED:
            raise ValueError("No se puede activar una cuenta retirada")
        self.status = AccountStatus.ACTIVE
        self.updated_at = _utcnow()

    def mark_degraded(self) -> None:
        self.status = AccountStatus.DEGRADED
        self.updated_at = _utcnow()

    def suspend(self) -> None:
        if self.status == AccountStatus.RETIRED:
            raise ValueError("No se puede suspender una cuenta retirada")
        self.status = AccountStatus.SUSPENDED
        self.updated_at = _utcnow()

    def disconnect(self) -> None:
        self.status = AccountStatus.DISCONNECTED
        self.updated_at = _utcnow()

    def retire(self) -> None:
        self.status = AccountStatus.RETIRED
        self.updated_at = _utcnow()

    def is_usable(self) -> bool:
        """True si la cuenta puede enviar/recibir mensajes hoy."""
        return self.status in (AccountStatus.ACTIVE, AccountStatus.DEGRADED)


@dataclass
class WhatsAppProviderConfiguration:
    """Configuración técnica del proveedor para una cuenta (§10).

    Deliberadamente mínima en WA-2: solo lo que ya se necesita para
    describir "qué versión de API y qué parámetros extra usa esta cuenta".
    Los secretos (tokens, app secret) NUNCA viven aquí — solo una
    referencia (`secret_reference_id`, ya en `WhatsAppBusinessAccount`) al
    `SecretStore` (WA-1).
    """

    id: str
    account_id: str
    provider: WhatsAppProvider
    api_version: str
    extra_settings: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        provider: WhatsAppProvider,
        api_version: str,
        extra_settings: Optional[Dict[str, Any]] = None,
    ) -> "WhatsAppProviderConfiguration":
        if not account_id:
            raise ValueError("account_id es obligatorio")
        if not api_version or not api_version.strip():
            raise ValueError("api_version es obligatorio")
        now = _utcnow()
        return cls(
            id=new_id(),
            account_id=account_id,
            provider=provider,
            api_version=api_version.strip(),
            extra_settings=dict(extra_settings or {}),
            created_at=now,
            updated_at=now,
        )
