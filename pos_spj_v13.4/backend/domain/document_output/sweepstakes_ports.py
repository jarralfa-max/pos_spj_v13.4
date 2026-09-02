"""SweepstakesTicketPort — SET-15 "Integración con Sweepstakes". Distinct
from `routing_ports.py` (which device prints) and `rendering_ports.py`
(bytes-out): this is the contract a wiring-layer adapter over
`core/services/loyalty_service.py::LoyaltyService` (the real owner of
raffle/boleto business rules — budget reservation, activation, ticket
generation eligibility, winner selection, all real §FASE 3 financial
validators) would implement, to fetch a `SweepstakesTicketData` for
printing/reprinting a boleto.

**No real implementation here, still** — but NOT for the reason
originally documented in this file. A SET-15 cutover (2026-08-23) audited
the claim below against the actual code and found it doesn't hold:
`LoyaltyService.issue_raffle_tickets_for_sale()`/`process_raffles_for_sale()`
convert every id to a plain string immediately and never join against a
legacy table by `venta_id` — eligibility, ticket generation, and lookup
are all keyed on `(raffle_id, venta_id)` as opaque strings in
`raffle_tickets`. A real UUIDv7 `sale.id` works with zero identity
bridging, confirmed by wiring `sales_pos`'s real checkout/reprint flow
directly to `LoyaltyService` via
`backend/infrastructure/integrations/sales_sweepstakes_client.py::
SalesSweepstakesClient` (issuance at checkout, printing via reprint,
both using the real, already-live `PrinterService.print_raffle_ticket()`
— no `document_output` template/render pipeline involved).

This port is a DIFFERENT shape than what that cutover needed — it's
designed around fetching a single ticket by number for
`document_output`'s own template/render pipeline (`DocumentRendererPort`,
still no real implementation, same boundary as SET-10/11's hardware/
rendering ports), not issuing+printing via the legacy renderer. Building
a real adapter for THIS port specifically remains undone — not because
of a legacy-id blocker (disproven), but because `document_output`'s own
sweepstakes capability still has zero application callers, same as its
label/ticket capabilities generally. Reprints compose with this port
exactly the same way as any other document type
(`policies/reprint_policy.py` is document_type-agnostic, proven in
tests), so nothing about "Reimpresión" required new code here either —
that finding was correct in the original audit and still holds.

~~Original (2026-XX-XX, superseded) reasoning, kept for history~~:
"`LoyaltyService`'s raffle methods still key everything on legacy
integer ids (`venta_id: int`, `sucursal_id: int`) — this bounded context
is UUIDv7-only (REGLA CERO). Bridging that boundary safely means
deciding how/where the int↔UUID translation happens, which is a decision
for whoever migrates the Loyalty/Sweepstakes domain itself" — this
claim did not match `issue_raffle_tickets_for_sale`'s actual body when
re-read; see the SET-15 cutover note above.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.document_output.value_objects.sweepstakes_ticket_data import SweepstakesTicketData


class SweepstakesTicketPort(Protocol):
    def get_ticket(self, ticket_number: str) -> SweepstakesTicketData:
        """Fetch the boleto data needed to print/reprint one sweepstakes
        ticket. Must raise rather than return a partial/placeholder
        result when the ticket number doesn't exist — the caller does
        not catch or paper over a lookup failure."""
        ...
