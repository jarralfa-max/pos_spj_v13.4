# domain/whatsapp/entities/channel_number.py — WA-2 (prompt maestro §10-11)
"""WhatsAppChannelNumber — un número de WhatsApp asociado a una cuenta."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import ChannelNumberStatus, ChannelRole
from domain.whatsapp.exceptions import InvalidChannelNumberStateError
from domain.whatsapp.value_objects.phone_number import WhatsAppPhoneNumber


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WhatsAppChannelNumber:
    id: str
    account_id: str
    phone_number_external_id: str
    display_phone_number: str
    normalized_phone_number: WhatsAppPhoneNumber
    branch_id: Optional[str]
    channel_role: ChannelRole
    status: ChannelNumberStatus
    timezone: str
    locale: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        phone_number_external_id: str,
        display_phone_number: str,
        channel_role: ChannelRole,
        branch_id: Optional[str] = None,
        timezone_name: str = "America/Mexico_City",
        locale: str = "es-MX",
    ) -> "WhatsAppChannelNumber":
        if not account_id:
            raise ValueError("account_id es obligatorio")
        if not phone_number_external_id or not phone_number_external_id.strip():
            raise ValueError("phone_number_external_id es obligatorio")
        # §11 del prompt maestro: "no asumir sucursal Principal" — solo el
        # rol GLOBAL_CUSTOMER_SERVICE puede no tener sucursal fija; para
        # todos los demás roles, branch_id es obligatorio en el borde del
        # dominio, no una inferencia posterior.
        if channel_role != ChannelRole.GLOBAL_CUSTOMER_SERVICE and not branch_id:
            raise ValueError(
                f"branch_id es obligatorio para channel_role={channel_role.value} "
                "(solo GLOBAL_CUSTOMER_SERVICE puede no tener sucursal fija)"
            )
        normalized = WhatsAppPhoneNumber.from_raw(display_phone_number)
        now = _utcnow()
        return cls(
            id=new_id(),
            account_id=account_id,
            phone_number_external_id=phone_number_external_id.strip(),
            display_phone_number=display_phone_number,
            normalized_phone_number=normalized,
            branch_id=branch_id,
            channel_role=channel_role,
            status=ChannelNumberStatus.DRAFT,
            timezone=timezone_name,
            locale=locale,
            created_at=now,
            updated_at=now,
        )

    def is_global(self) -> bool:
        return self.channel_role == ChannelRole.GLOBAL_CUSTOMER_SERVICE

    def is_usable(self) -> bool:
        return self.status in (ChannelNumberStatus.ACTIVE, ChannelNumberStatus.DEGRADED)

    def _assert_not_retired(self, action: str) -> None:
        if self.status == ChannelNumberStatus.RETIRED:
            raise InvalidChannelNumberStateError(
                f"No se puede {action} un número retirado (id={self.id})"
            )

    def activate(self) -> None:
        self._assert_not_retired("activar")
        self.status = ChannelNumberStatus.ACTIVE
        self.updated_at = _utcnow()

    def mark_degraded(self) -> None:
        self._assert_not_retired("degradar")
        self.status = ChannelNumberStatus.DEGRADED
        self.updated_at = _utcnow()

    def suspend(self) -> None:
        self._assert_not_retired("suspender")
        self.status = ChannelNumberStatus.SUSPENDED
        self.updated_at = _utcnow()

    def disconnect(self) -> None:
        self._assert_not_retired("desconectar")
        self.status = ChannelNumberStatus.DISCONNECTED
        self.updated_at = _utcnow()

    def retire(self) -> None:
        self.status = ChannelNumberStatus.RETIRED
        self.updated_at = _utcnow()
