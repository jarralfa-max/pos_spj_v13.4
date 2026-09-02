"""LoyaltyCardsUnitOfWork — one transaction boundary for the Loyalty Cards
context. Mirrors
backend/infrastructure/db/repositories/sweepstakes/unit_of_work.py exactly."""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.loyalty_cards.card_repository import (
    LoyaltyCardRepository,
    LoyaltyCardTokenRepository,
)
from backend.infrastructure.db.repositories.loyalty_cards.batch_repository import (
    LoyaltyCardBatchItemRepository,
    LoyaltyCardBatchRepository,
)
from backend.infrastructure.db.repositories.loyalty_cards.digital_card_repository import (
    LoyaltyDigitalCardProjectionRepository,
)
from backend.infrastructure.db.repositories.loyalty_cards.outbox_repository import (
    LoyaltyCardsOutboxRepository,
)
from backend.infrastructure.db.repositories.loyalty_cards.print_job_repository import (
    LoyaltyCardPrintJobRepository,
)
from backend.infrastructure.db.repositories.loyalty_cards.sheet_repository import (
    LoyaltyCardImpositionProfileRepository,
    LoyaltyCardSheetProfileRepository,
)
from backend.infrastructure.db.repositories.loyalty_cards.template_repository import (
    LoyaltyCardTemplateRepository,
    LoyaltyCardTemplateVersionRepository,
)


class LoyaltyCardsUnitOfWork:
    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
        self.cards = LoyaltyCardRepository(connection)
        self.tokens = LoyaltyCardTokenRepository(connection)
        self.templates = LoyaltyCardTemplateRepository(connection)
        self.template_versions = LoyaltyCardTemplateVersionRepository(connection)
        self.sheet_profiles = LoyaltyCardSheetProfileRepository(connection)
        self.imposition_profiles = LoyaltyCardImpositionProfileRepository(connection)
        self.batches = LoyaltyCardBatchRepository(connection)
        self.batch_items = LoyaltyCardBatchItemRepository(connection)
        self.print_jobs = LoyaltyCardPrintJobRepository(connection)
        self.digital_projections = LoyaltyDigitalCardProjectionRepository(connection)
        self.outbox = LoyaltyCardsOutboxRepository(connection)
        self._completed = False

    def __enter__(self) -> "LoyaltyCardsUnitOfWork":
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
