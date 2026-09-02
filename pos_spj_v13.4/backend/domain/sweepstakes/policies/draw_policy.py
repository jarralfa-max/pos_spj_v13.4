"""SweepstakesDrawPolicy — pure functions for computing the eligible ticket
pool a draw selects from (master prompt §27-28). No repository/IO here —
callers pass in already-loaded tickets."""

from __future__ import annotations

import hashlib

from backend.domain.sweepstakes.entities.sweepstakes_ticket import SweepstakesTicket


class SweepstakesDrawPolicy:
    @staticmethod
    def eligible_tickets(
        tickets: list[SweepstakesTicket], *, exclude_ticket_ids: frozenset[str] = frozenset(),
    ) -> list[SweepstakesTicket]:
        """A ticket is eligible if it is not VOID and has not already won in
        this campaign (`exclude_ticket_ids` — prior winners, so the same
        ticket is not drawn twice across multiple prizes in one draw)."""
        return [t for t in tickets if t.is_eligible() and t.id not in exclude_ticket_ids]

    @staticmethod
    def pool_hash(tickets: list[SweepstakesTicket]) -> str:
        """A reproducible fingerprint of the exact eligible pool a draw ran
        against, for later independent audit (mirrors the legacy
        `raffle_winners.pool_hash` field's own intent)."""
        ordered_ids = sorted(t.id for t in tickets)
        digest = hashlib.sha256("|".join(ordered_ids).encode("utf-8"))
        return digest.hexdigest()
