"""CustomerCreditUnitOfWork — one transaction boundary for the Customer
Credit context. Mirrors
backend/infrastructure/db/repositories/customer_service/unit_of_work.py.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.customer_credit.customer_credit_profile_repository import (
    CustomerCreditProfileRepository,
)
from backend.infrastructure.db.repositories.customer_credit.support_repositories import (
    CustomerCreditAuditRepository,
    CustomerCreditOutboxRepository,
    CustomerCreditProcessedEventRepository,
)


class CustomerCreditUnitOfWork:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.profiles = CustomerCreditProfileRepository(connection)
        self.audit = CustomerCreditAuditRepository(connection)
        self.outbox = CustomerCreditOutboxRepository(connection)
        self.processed_events = CustomerCreditProcessedEventRepository(connection)
        self._completed = False

    def __enter__(self) -> "CustomerCreditUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        rollback = getattr(self.connection, "rollback", None)
        if rollback is not None:
            rollback()
        self._completed = True
