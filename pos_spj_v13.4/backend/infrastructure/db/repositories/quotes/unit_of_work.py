"""QuotesUnitOfWork — una transacción por caso de uso (commit al salir sin error)."""

from __future__ import annotations

from backend.infrastructure.db.repositories.quotes.quote_repository import (
    QuoteAuditRepository,
    QuoteOutboxRepository,
    QuoteRepository,
)
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class QuotesUnitOfWork(TransactionalUnitOfWork):
    def __init__(self, connection) -> None:
        self.connection = connection
        self.quotes = QuoteRepository(connection)
        self.audit = QuoteAuditRepository(connection)
        self.outbox = QuoteOutboxRepository(connection)
