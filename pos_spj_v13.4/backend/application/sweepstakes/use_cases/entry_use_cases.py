"""Sweepstakes entry/ticket use cases (LOY-15, master prompt §27-28).

§28's own rule — "no debe existir boleto sin folio/derecho previo",
reprints never duplicate an entry — is enforced here, at the application
layer: `IssueSweepstakesTicketUseCase` looks up the `SweepstakesEntry` FIRST
and fails closed if it does not exist or belongs to a different campaign;
`PrintSweepstakesTicketUseCase` always mutates the SAME ticket row
(`SweepstakesTicket.record_print()`) — it never creates a new ticket, so a
reprint can never produce a second entry's worth of chances.
"""

from __future__ import annotations

from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.sweepstakes.result import SweepstakesResult, fail_from_domain_error
from backend.application.sweepstakes.use_cases._base import _SweepstakesBaseUseCase
from backend.domain.loyalty.events import SYSTEM_ACTOR_ID
from backend.domain.sweepstakes.entities.sweepstakes_entry import SweepstakesEntry
from backend.domain.sweepstakes.entities.sweepstakes_ticket import SweepstakesTicket
from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
from backend.domain.sweepstakes.events import SweepstakesEvents
from backend.domain.sweepstakes.exceptions import (
    InvalidSweepstakesCampaignStateError,
    SweepstakesCampaignNotFoundError,
    SweepstakesDomainError,
    SweepstakesEntryNotFoundError,
    SweepstakesTicketNotFoundError,
    TicketRequiresExistingEntryError,
)
from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import SweepstakesUnitOfWork


class GrantSweepstakesEntryUseCase(_SweepstakesBaseUseCase):
    """Manual grant path (`SweepstakesEntryMethod.MANUAL_GRANT` and any other
    method a human operator records by hand). Automatic granting from a real
    sale (`PURCHASE_AMOUNT`/`PRODUCT_PURCHASE`) requires a Sales integration
    hook that does not exist yet (honest gap, same shape as LOY-14's own
    documented COUPON/VOUCHER birthday-benefit gap) — this use case is the
    only way to grant an entry today, called either by a human operator or,
    once that hook exists, by a system-triggered caller passing its own
    `entry_method`."""

    def execute(
        self, connection, *, campaign_id: str, customer_id: str,
        entry_method: SweepstakesEntryMethod, actor_user_id: str, operation_id: str,
        **entry_kwargs,
    ) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_MANAGE)
            with SweepstakesUnitOfWork(connection) as uow:
                campaign = uow.campaigns.get(campaign_id)
                if campaign is None:
                    return fail_from_domain_error(
                        SweepstakesCampaignNotFoundError(f"Campaña {campaign_id} no existe"),
                        operation_id=operation_id)
                if not campaign.accepts_entries():
                    return fail_from_domain_error(
                        InvalidSweepstakesCampaignStateError(
                            "La campaña debe estar ACTIVE para otorgar derechos"),
                        operation_id=operation_id)
                entry = SweepstakesEntry.grant(
                    campaign_id, customer_id, entry_method,
                    granted_by_user_id=actor_user_id, **entry_kwargs)
                uow.entries.add(entry)
                self._emit(uow, SweepstakesEvents.ENTRY_GRANTED, entity_id=entry.id,
                           operation_id=operation_id, branch_id=campaign.branch_id or actor_user_id,
                           actor_user_id=actor_user_id)
            return SweepstakesResult.ok(
                "Derecho de participación otorgado", entity_id=entry.id, operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class GrantSweepstakesEntryFromSaleUseCase(_SweepstakesBaseUseCase):
    """LOY-24 (§54): the Sales integration hook LOY-15 flagged as missing.
    System-triggered by a completed sale — no live authenticated staff
    session performs "grant a sweepstakes entry" as its own action, so this
    never gates on `self._auth.require()` and never routes through
    `GrantSweepstakesEntryUseCase` (same "system sweep never calls a
    permission-gated use case" discipline as Loyalty's own
    `GrantBirthdayBenefitUseCase`, LOY-14) — it builds the `SweepstakesEntry`
    directly within its own transaction.

    Silently grants ZERO chances (success, `granted=False`) rather than an
    error when the campaign's rule isn't `PURCHASE_AMOUNT`, doesn't accept
    entries right now, or the sale amount doesn't clear one ticket's
    threshold — a sale should never fail or even log a warning just because
    it didn't happen to qualify for a promotion running at the same time.
    """

    def execute(
        self, connection, *, campaign_id: str, customer_id: str, source_sale_id: str,
        sale_amount, actor_branch_id: str, operation_id: str,
    ) -> SweepstakesResult:
        try:
            with SweepstakesUnitOfWork(connection) as uow:
                campaign = uow.campaigns.get(campaign_id)
                if campaign is None:
                    return fail_from_domain_error(
                        SweepstakesCampaignNotFoundError(f"Campaña {campaign_id} no existe"),
                        operation_id=operation_id)
                if not campaign.accepts_entries():
                    return SweepstakesResult.ok(
                        "La campaña no está activa", operation_id=operation_id, granted=False)
                rule = uow.rules.get_by_campaign(campaign_id)
                if rule is None or rule.entry_method is not SweepstakesEntryMethod.PURCHASE_AMOUNT:
                    return SweepstakesResult.ok(
                        "La campaña no otorga derechos por monto de compra",
                        operation_id=operation_id, granted=False)
                chances = rule.chances_for_amount(sale_amount)
                if chances <= 0:
                    return SweepstakesResult.ok(
                        "El monto de la venta no alcanza para un derecho", operation_id=operation_id,
                        granted=False)
                if campaign.max_tickets_per_customer > 0:
                    already_granted = sum(
                        entry.chances_granted
                        for entry in uow.entries.list_for_customer(campaign_id, customer_id))
                    chances = min(chances, max(campaign.max_tickets_per_customer - already_granted, 0))
                    if chances <= 0:
                        return SweepstakesResult.ok(
                            "El cliente ya alcanzó el máximo de derechos permitidos",
                            operation_id=operation_id, granted=False)

                entry = SweepstakesEntry.grant(
                    campaign_id, customer_id, SweepstakesEntryMethod.PURCHASE_AMOUNT,
                    chances_granted=chances, source_sale_id=source_sale_id)
                uow.entries.add(entry)
                self._emit(uow, SweepstakesEvents.ENTRY_GRANTED, entity_id=entry.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=SYSTEM_ACTOR_ID, source_sale_id=source_sale_id,
                           chances_granted=chances)
            return SweepstakesResult.ok(
                "Derecho otorgado por compra", entity_id=entry.id, operation_id=operation_id,
                granted=True, chances_granted=chances)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class IssueSweepstakesTicketUseCase(_SweepstakesBaseUseCase):
    def execute(
        self, connection, *, campaign_id: str, entry_id: str, actor_user_id: str,
        operation_id: str,
    ) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_MANAGE)
            with SweepstakesUnitOfWork(connection) as uow:
                campaign = uow.campaigns.get(campaign_id)
                if campaign is None:
                    return fail_from_domain_error(
                        SweepstakesCampaignNotFoundError(f"Campaña {campaign_id} no existe"),
                        operation_id=operation_id)
                entry = uow.entries.get(entry_id)
                if entry is None:
                    return fail_from_domain_error(
                        SweepstakesEntryNotFoundError(f"Derecho {entry_id} no existe"),
                        operation_id=operation_id)
                if entry.campaign_id != campaign_id:
                    return fail_from_domain_error(
                        TicketRequiresExistingEntryError(
                            "El derecho pertenece a otra campaña"),
                        operation_id=operation_id)
                already_issued = uow.tickets.count_for_entry(entry_id)
                if already_issued >= entry.chances_granted:
                    return fail_from_domain_error(
                        TicketRequiresExistingEntryError(
                            "El derecho ya emitió todos sus boletos disponibles"),
                        operation_id=operation_id)
                if campaign.max_tickets_per_customer > 0:
                    current = uow.tickets.count_for_customer(campaign_id, entry.customer_id)
                    if current >= campaign.max_tickets_per_customer:
                        return fail_from_domain_error(
                            InvalidSweepstakesCampaignStateError(
                                "El cliente alcanzó el máximo de boletos permitidos"),
                            operation_id=operation_id)
                sequence = uow.tickets.count_for_campaign(campaign_id) + 1
                ticket_number = f"{campaign.code}-{sequence:06d}"
                ticket = SweepstakesTicket.issue(
                    campaign_id, entry_id, entry.customer_id, ticket_number)
                uow.tickets.save(ticket)
                self._emit(uow, SweepstakesEvents.TICKET_ISSUED, entity_id=ticket.id,
                           operation_id=operation_id, branch_id=campaign.branch_id or actor_user_id,
                           actor_user_id=actor_user_id, ticket_number=ticket_number)
            return SweepstakesResult.ok(
                "Boleto emitido", entity_id=ticket.id, operation_id=operation_id,
                ticket_number=ticket_number)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class PrintSweepstakesTicketUseCase(_SweepstakesBaseUseCase):
    def execute(self, connection, *, ticket_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> SweepstakesResult:
        try:
            with SweepstakesUnitOfWork(connection) as uow:
                ticket = uow.tickets.get(ticket_id)
                if ticket is None:
                    return fail_from_domain_error(
                        SweepstakesTicketNotFoundError(f"Boleto {ticket_id} no existe"),
                        operation_id=operation_id)
                is_reprint = ticket.print_count > 0
                self._auth.require(
                    actor_user_id,
                    LoyaltyPermissions.SWEEPSTAKES_TICKET_REPRINT if is_reprint
                    else LoyaltyPermissions.SWEEPSTAKES_TICKET_PRINT)
                ticket.record_print()
                uow.tickets.save(ticket)
                self._emit(uow, SweepstakesEvents.TICKET_PRINTED, entity_id=ticket.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, print_count=ticket.print_count,
                           is_reprint=is_reprint)
            return SweepstakesResult.ok(
                "Boleto reimpreso" if is_reprint else "Boleto impreso",
                entity_id=ticket.id, operation_id=operation_id, print_count=ticket.print_count)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class VoidSweepstakesTicketUseCase(_SweepstakesBaseUseCase):
    def execute(self, connection, *, ticket_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> SweepstakesResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.SWEEPSTAKES_MANAGE)
            with SweepstakesUnitOfWork(connection) as uow:
                ticket = uow.tickets.get(ticket_id)
                if ticket is None:
                    return fail_from_domain_error(
                        SweepstakesTicketNotFoundError(f"Boleto {ticket_id} no existe"),
                        operation_id=operation_id)
                ticket.void(reason)
                uow.tickets.save(ticket)
                self._emit(uow, SweepstakesEvents.TICKET_VOIDED, entity_id=ticket.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, reason=reason)
            return SweepstakesResult.ok("Boleto anulado", entity_id=ticket.id,
                                         operation_id=operation_id)
        except SweepstakesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
