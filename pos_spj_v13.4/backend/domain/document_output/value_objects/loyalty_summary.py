"""LoyaltySummary — SET-13 "Loyalty summary": what a ticket shows about
the customer's loyalty account. Generalizes the legacy
`core/tickets/ticket_print_model.py::TicketLoyaltyInfo`. Purely factual
account state (points earned this sale, current balance, tier) — not a
"claim" subject to `marketing_claim_validation_policy`, unlike FOMO
campaign messages.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.document_output.exceptions import DocumentInvalidValueError


@dataclass(frozen=True, slots=True)
class LoyaltySummary:
    points_earned: int | None = None
    points_balance: int | None = None
    tier: str = ""
    available: bool = False

    @classmethod
    def create(
        cls, *, points_earned: int | None = None, points_balance: int | None = None,
        tier: str = "", available: bool = False,
    ) -> "LoyaltySummary":
        for field_name, value in (("points_earned", points_earned), ("points_balance", points_balance)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise DocumentInvalidValueError(
                    f"{field_name} debe ser un entero >= 0 o None, recibido {value!r}"
                )
        return cls(
            points_earned=points_earned, points_balance=points_balance, tier=tier.strip(),
            available=bool(available),
        )
