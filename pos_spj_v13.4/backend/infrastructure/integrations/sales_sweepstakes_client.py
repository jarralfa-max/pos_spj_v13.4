"""SalesSweepstakesClient — el punto por donde Ventas habla con Sorteos.

Dos operaciones: al cobrar, otorgar los derechos que la compra genere y emitir
sus boletos; al imprimir, recuperar los boletos de esa venta.

QUÉ CAMBIÓ
----------
Envolvía `core/services/loyalty_service.py::LoyaltyService`, borrado, para el
modelo LEGACY de rifas. No se reconstruyó, y aquí la razón es más contundente
que en otros casos: ese modelo **no tiene esquema en este repositorio**. No hay
migración que cree sus tablas ni nada que las escriba — vivía entero dentro de
`core/`. Las llamadas legacy no operaban ya sobre nada.

El contexto acotado canónico `sweepstakes` sí existe, con campañas, reglas,
derechos, boletos y sorteos. Este archivo YA lo usaba a medias: otorgaba los
derechos por la vía canónica y, a la vez, llamaba al modelo legacy.

EL HUECO QUE SE CIERRA
----------------------
Otorgar un derecho y emitir un boleto son pasos distintos, y sólo el primero
estaba conectado. El cliente acumulaba derechos y no recibía ningún boleto: no
fallaba nada, simplemente el ticket de compra salía sin boletos y la consulta
de imprimibles devolvía vacío siempre. Ahora, tras otorgar, se emiten.

NUNCA BLOQUEA EL COBRO. Un fallo de sorteos —campaña mal configurada, tope
alcanzado, error de base— no puede tumbar una venta que ya se pagó. Lo mismo
que ya hace el resto de integraciones de la caja.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from backend.application.sales.dto import SaleDTO


class SalesSweepstakesClient:
    def __init__(self, connection) -> None:
        self._connection = connection

    # ── al cobrar ────────────────────────────────────────────────────────
    def issue_tickets_for_sale(self, *, sale: "SaleDTO") -> None:
        """Otorga los derechos de esta venta y emite sus boletos.

        Sin cliente identificado no hay a quién otorgarle nada: una venta a
        público general no participa, y eso es normal, no un error.
        """
        if not sale.customer_id:
            return

        from backend.application.sweepstakes.use_cases.entry_use_cases import (
            GrantSweepstakesEntryFromSaleUseCase,
            IssueSweepstakesTicketsFromSaleUseCase,
        )
        from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import (
            SweepstakesUnitOfWork,
        )
        from backend.shared.ids import new_uuid

        with SweepstakesUnitOfWork(self._connection) as uow:
            campaigns = uow.campaigns.list_active()

        conceder = GrantSweepstakesEntryFromSaleUseCase()
        emitir = IssueSweepstakesTicketsFromSaleUseCase()
        for campaign in campaigns:
            resultado = conceder.execute(
                self._connection, campaign_id=campaign.id, customer_id=sale.customer_id,
                source_sale_id=sale.id, sale_amount=sale.total,
                actor_branch_id=sale.branch_id, operation_id=new_uuid())
            # `granted=False` es una respuesta normal: la venta no alcanzó el
            # monto, la campaña no otorga por compra, o el cliente ya llegó a
            # su tope. No hay derecho que convertir en boletos.
            if not resultado.success or not resultado.data.get("granted"):
                continue
            emitir.execute(
                self._connection, entry_id=resultado.entity_id,
                actor_branch_id=sale.branch_id, operation_id=new_uuid())

    # ── al imprimir ──────────────────────────────────────────────────────
    def get_printable_tickets_for_sale(self, *, sale_id: str) -> list[dict]:
        """Boletos de esta venta, listos para imprimir.

        Devuelve diccionarios y no entidades porque quien llama se los pasa
        tal cual al servicio de impresión, que es código de frontera.
        """
        from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import (
            SweepstakesUnitOfWork,
        )

        with SweepstakesUnitOfWork(self._connection) as uow:
            tickets = uow.tickets.list_for_sale(sale_id)
            if not tickets:
                return []
            # Las campañas se resuelven una sola vez: una venta puede generar
            # varios boletos de la MISMA campaña, y consultarla por boleto
            # sería una consulta por papel impreso.
            campañas = {}
            for ticket in tickets:
                if ticket.campaign_id not in campañas:
                    campañas[ticket.campaign_id] = uow.campaigns.get(ticket.campaign_id)
            premios = {
                campaign_id: uow.prizes.list_for_campaign(campaign_id)
                for campaign_id in campañas
            }
            # La fecha del sorteo NO está en la campaña: vive en su
            # `SweepstakesDraw`, que es otra entidad. Buscarla en la campaña
            # devolvería vacío siempre y el boleto saldría impreso sin fecha.
            sorteos = {
                campaign_id: self._scheduled_draw(uow, campaign_id)
                for campaign_id in campañas
            }

        return [
            self._printable(ticket, campañas.get(ticket.campaign_id),
                            premios.get(ticket.campaign_id) or [],
                            sorteos.get(ticket.campaign_id), sale_id)
            for ticket in tickets
        ]

    @staticmethod
    def _scheduled_draw(uow, campaign_id: str):
        """El sorteo pendiente más próximo de la campaña, si hay alguno.

        Una campaña puede tener varios sorteos programados; al boleto le
        corresponde el siguiente, no el primero que devuelva la base.
        """
        pendientes = [
            draw for draw in uow.draws.list_for_campaign(campaign_id)
            if draw.scheduled_at and not draw.executed_at
        ]
        return min(pendientes, key=lambda d: d.scheduled_at) if pendientes else None

    @staticmethod
    def _printable(ticket, campaign, prizes, draw, sale_id: str) -> dict[str, Any]:
        """Carga del boleto, con los campos que el renderizador espera.

        Se nombra el PRIMER premio de la campaña, que es el mayor por
        convención de la pantalla que los captura. Un boleto sin premio
        nombrado o sin sorteo programado sigue siendo válido —participa
        igual— así que la ausencia se deja vacía en vez de impedir la
        impresión.
        """
        return {
            "raffle_id": ticket.campaign_id,
            "raffle_name": getattr(campaign, "name", "") if campaign else "",
            "ticket_number": ticket.ticket_number,
            "prize": getattr(prizes[0], "name", "") if prizes else "",
            "draw_date": getattr(draw, "scheduled_at", "") or "" if draw else "",
            "customer_id": ticket.customer_id,
            "sale_reference": sale_id,
        }
