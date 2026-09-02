# domain/whatsapp/entities/identity.py — WA-2 (prompt maestro §12)
"""WhatsAppIdentity — identidad del canal, distinta del cliente ERP.

El teléfono no es PK (§12). La identidad WhatsApp puede vincularse a un
cliente (`customer_id`), pero nunca lo reemplaza — Customers sigue siendo
dueño de la identidad de negocio (§44).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import IdentityStatus
from domain.whatsapp.value_objects.phone_number import WhatsAppPhoneNumber


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WhatsAppIdentity:
    id: str
    wa_id: str
    normalized_phone: WhatsAppPhoneNumber
    customer_id: Optional[str]
    identity_status: IdentityStatus
    first_seen_at: datetime
    last_seen_at: datetime
    blocked_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, wa_id: str, raw_phone: str) -> "WhatsAppIdentity":
        if not wa_id or not wa_id.strip():
            raise ValueError("wa_id es obligatorio")
        normalized = WhatsAppPhoneNumber.from_raw(raw_phone)
        now = _utcnow()
        return cls(
            id=new_id(),
            wa_id=wa_id.strip(),
            normalized_phone=normalized,
            customer_id=None,
            identity_status=IdentityStatus.UNRESOLVED,
            first_seen_at=now,
            last_seen_at=now,
            blocked_at=None,
            created_at=now,
            updated_at=now,
        )

    def touch(self) -> None:
        """Registra actividad nueva de esta identidad (mensaje recibido)."""
        self.last_seen_at = _utcnow()
        self.updated_at = self.last_seen_at

    def link_to_customer(self, customer_id: str) -> None:
        if not customer_id:
            raise ValueError("customer_id es obligatorio para vincular")
        self.customer_id = customer_id
        if self.identity_status == IdentityStatus.UNRESOLVED:
            self.identity_status = IdentityStatus.RESOLVED
        self.updated_at = _utcnow()

    def verify(self) -> None:
        if not self.customer_id:
            raise ValueError("No se puede verificar una identidad sin cliente vinculado")
        self.identity_status = IdentityStatus.VERIFIED
        self.updated_at = _utcnow()

    def block(self) -> None:
        self.identity_status = IdentityStatus.BLOCKED
        self.blocked_at = _utcnow()
        self.updated_at = self.blocked_at

    def unblock(self) -> None:
        """Desbloquea la identidad.

        No reconstruye si estaba VERIFIED antes del bloqueo (esta entidad no
        guarda ese historial) — vuelve a RESOLVED si tiene cliente vinculado,
        o UNRESOLVED si no. Una re-verificación explícita puede llamarse
        después si corresponde.
        """
        if self.identity_status != IdentityStatus.BLOCKED:
            return
        self.identity_status = (
            IdentityStatus.RESOLVED if self.customer_id else IdentityStatus.UNRESOLVED
        )
        self.blocked_at = None
        self.updated_at = _utcnow()

    def merge_into(self, other_id: str) -> None:
        """Marca esta identidad como fusionada dentro de `other_id`.

        La operación de reasignar mensajes/conversaciones del ID viejo al
        nuevo es responsabilidad del repositorio/aplicación (WA-4+); esta
        entidad solo registra su propio estado terminal.
        """
        if not other_id:
            raise ValueError("other_id es obligatorio")
        if other_id == self.id:
            raise ValueError("Una identidad no puede fusionarse consigo misma")
        self.identity_status = IdentityStatus.MERGED
        self.updated_at = _utcnow()

    def is_blocked(self) -> bool:
        return self.identity_status == IdentityStatus.BLOCKED
