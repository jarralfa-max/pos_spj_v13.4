"""QuotesUnitOfWork — una transacción por caso de uso (commit al salir sin error)."""

from __future__ import annotations

from backend.infrastructure.db.repositories.quotes.quote_repository import (
    QuoteAuditRepository,
    QuoteOutboxRepository,
    QuoteRepository,
)


class QuotesUnitOfWork:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.quotes = QuoteRepository(connection)
        self.audit = QuoteAuditRepository(connection)
        self.outbox = QuoteOutboxRepository(connection)

    def __enter__(self) -> "QuotesUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        return False
