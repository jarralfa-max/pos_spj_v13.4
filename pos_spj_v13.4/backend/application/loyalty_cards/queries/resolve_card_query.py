"""ResolveLoyaltyCardQuery — qué tarjeta es la que se escaneó (§49).

El punto de venta (y WhatsApp, y la pantalla «QR y validación») entrega lo que
leyó el escáner —el QR (`SPJ-CARD:<token>`), el código de barras o el número
impreso— y recibe el estado de la tarjeta, la cuenta y la membresía a las que
pertenece, el programa, el nivel, si puede usarse y por qué no. Nunca consulta
las tablas de tarjetas por su cuenta.

Hasta LOY-29 el POS buscaba el código SÓLO en la tabla legacy `clientes`, así
que una tarjeta emitida por el módulo canónico nunca identificaba al cliente.

Elegibilidad: una tarjeta ACTIVA identifica al cliente y puede acumular/canjear.
Una EMITIDA sin activar lo identifica pero con advertencia (§46). Bloqueada,
repuesta, cancelada o vencida: no identifica a nadie — y un QR rotado o
revocado tampoco, aunque la tarjeta siga activa (§32).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.loyalty_cards.enums import LoyaltyCardStatus
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork

QR_PREFIX = "SPJ-CARD:"

_IDENTIFICA = (LoyaltyCardStatus.ACTIVE, LoyaltyCardStatus.ISSUED)
_MOTIVOS = {
    LoyaltyCardStatus.BLOCKED: "La tarjeta está bloqueada.",
    LoyaltyCardStatus.REPLACED: "La tarjeta fue repuesta; usa la tarjeta nueva.",
    LoyaltyCardStatus.CANCELLED: "La tarjeta está cancelada.",
    LoyaltyCardStatus.EXPIRED: "La tarjeta está vencida.",
}


@dataclass(frozen=True)
class ResolvedLoyaltyCard:
    found: bool
    eligible: bool = False
    card_id: str | None = None
    card_number: str | None = None
    card_status: str | None = None
    customer_id: str | None = None
    loyalty_account_id: str | None = None
    membership_id: str | None = None
    program_name: str | None = None
    tier_name: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


def strip_qr_prefix(scanned: str) -> str:
    texto = str(scanned or "").strip()
    return texto[len(QR_PREFIX):] if texto.upper().startswith(QR_PREFIX) else texto


class ResolveLoyaltyCardQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def resolve(self, *, public_token: str | None = None, barcode: str | None = None,
                card_number: str | None = None) -> ResolvedLoyaltyCard:
        with LoyaltyCardsUnitOfWork(self._conn, owns_transaction=False) as uow:
            card, aviso_qr = None, None
            if public_token:
                token = uow.tokens.get_by_token(strip_qr_prefix(public_token))
                if token is not None:
                    card = uow.cards.get(token.card_id)
                    if not token.is_usable():
                        aviso_qr = "Este QR ya no es válido (fue rotado o revocado)."
            numero = (barcode or card_number or "").strip()
            if card is None and numero:
                card = uow.cards.get_by_number(numero)
        if card is None:
            return ResolvedLoyaltyCard(found=False, warnings=("Tarjeta no registrada.",))

        datos = self._membership(card.membership_id)
        avisos: list[str] = []
        elegible = card.status in _IDENTIFICA and aviso_qr is None
        if aviso_qr:
            avisos.append(aviso_qr)
        if card.status is LoyaltyCardStatus.ISSUED:
            avisos.append("La tarjeta aún no está activada.")
            elegible = False if aviso_qr else True
        if card.status in _MOTIVOS:
            avisos.append(_MOTIVOS[card.status])
        if datos and datos["membership_status"] != "ACTIVE":
            avisos.append("La membresía del cliente no está activa.")
        return ResolvedLoyaltyCard(
            found=True, eligible=elegible, card_id=card.id, card_number=card.card_number,
            card_status=card.status.value,
            customer_id=card.customer_id if elegible else None,
            loyalty_account_id=(datos or {}).get("account_id") if elegible else None,
            membership_id=card.membership_id if elegible else None,
            program_name=(datos or {}).get("program_name"),
            tier_name=(datos or {}).get("tier_name"), warnings=tuple(avisos))

    def _membership(self, membership_id: str) -> dict | None:
        fila = self._conn.execute(
            "SELECT m.loyalty_account_id, m.status, p.name, t.name FROM loyalty_memberships m"
            " LEFT JOIN loyalty_program_definitions p ON p.id = m.program_id"
            " LEFT JOIN loyalty_tiers t ON t.id = m.current_tier_id WHERE m.id = ?",
            (membership_id,)).fetchone()
        if fila is None:
            return None
        return {"account_id": fila[0], "membership_status": fila[1], "program_name": fila[2],
                "tier_name": fila[3]}


__all__ = ["QR_PREFIX", "ResolveLoyaltyCardQuery", "ResolvedLoyaltyCard", "strip_qr_prefix"]
