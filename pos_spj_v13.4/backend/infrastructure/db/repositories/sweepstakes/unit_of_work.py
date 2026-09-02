"""SweepstakesUnitOfWork — one transaction boundary for the Sweepstakes
context. Mirrors
backend/infrastructure/db/repositories/commercial_instruments/unit_of_work.py
exactly."""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.sweepstakes.campaign_repository import (
    SweepstakesCampaignRepository,
    SweepstakesPrizeRepository,
    SweepstakesRuleRepository,
)
from backend.infrastructure.db.repositories.sweepstakes.draw_repository import (
    SweepstakesDrawRepository,
    SweepstakesWinnerRepository,
)
from backend.infrastructure.db.repositories.sweepstakes.entry_repository import (
    SweepstakesEntryRepository,
    SweepstakesTicketRepository,
)
from backend.infrastructure.db.repositories.sweepstakes.outbox_repository import (
    SweepstakesOutboxRepository,
)


class SweepstakesUnitOfWork:
    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
        self.campaigns = SweepstakesCampaignRepository(connection)
        self.rules = SweepstakesRuleRepository(connection)
        self.prizes = SweepstakesPrizeRepository(connection)
        self.entries = SweepstakesEntryRepository(connection)
        self.tickets = SweepstakesTicketRepository(connection)
        self.draws = SweepstakesDrawRepository(connection)
        self.winners = SweepstakesWinnerRepository(connection)
        self.outbox = SweepstakesOutboxRepository(connection)
        self._completed = False

    def __enter__(self) -> "SweepstakesUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        if self._owns_transaction:
            self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        if self._owns_transaction:
            rollback = getattr(self.connection, "rollback", None)
            if rollback is not None:
                rollback()
        self._completed = True
