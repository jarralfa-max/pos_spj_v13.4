"""Vocabulario de Cotizaciones."""

from __future__ import annotations

from enum import Enum


class QuoteStatus(str, Enum):
    """Ciclo de vida.

    BORRADOR → (enviar a revisión) → POR APROBAR si algún precio va bajo lista,
    si no APROBADA → ENVIADA → ACEPTADA → CONVERTIDA (en Pedido).
    Desde ENVIADA/APROBADA: RECHAZADA por el cliente o VENCIDA por fecha.
    Cancelable mientras siga abierta.
    """

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    CONVERTED = "CONVERTED"


OPEN_STATUSES = frozenset({
    QuoteStatus.DRAFT, QuoteStatus.PENDING_APPROVAL, QuoteStatus.APPROVED,
    QuoteStatus.SENT, QuoteStatus.ACCEPTED,
})

#: Estados que vencen solos al pasar la vigencia. Un borrador no vence (se
#: corrige la fecha antes de enviarlo); una aceptada tampoco: el cliente ya
#: aceptó dentro de la vigencia.
EXPIRABLE_STATUSES = frozenset({
    QuoteStatus.PENDING_APPROVAL, QuoteStatus.APPROVED, QuoteStatus.SENT,
})

#: Estados desde los que se puede sacar una nueva versión.
REVISABLE_STATUSES = frozenset({
    QuoteStatus.APPROVED, QuoteStatus.SENT, QuoteStatus.REJECTED, QuoteStatus.EXPIRED,
})
