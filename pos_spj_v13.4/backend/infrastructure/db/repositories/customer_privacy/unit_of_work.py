"""CustomerPrivacyUnitOfWork — one transaction boundary for the Customer
Privacy context. Mirrors
backend/infrastructure/db/repositories/customer_credit/unit_of_work.py.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.customer_privacy.customer_communication_preference_repository import (
    CustomerCommunicationPreferenceRepository,
)
from backend.infrastructure.db.repositories.customer_privacy.customer_consent_repository import (
    CustomerConsentRepository,
)
from backend.infrastructure.db.repositories.customer_privacy.customer_data_retention_policy_repository import (
    CustomerDataRetentionPolicyRepository,
)
from backend.infrastructure.db.repositories.customer_privacy.customer_privacy_request_repository import (
    CustomerPrivacyRequestRepository,
)
from backend.infrastructure.db.repositories.customer_privacy.support_repositories import (
    CustomerPrivacyAuditRepository,
    CustomerPrivacyOutboxRepository,
    CustomerPrivacyProcessedEventRepository,
)


class CustomerPrivacyUnitOfWork:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.consents = CustomerConsentRepository(connection)
        self.preferences = CustomerCommunicationPreferenceRepository(connection)
        self.requests = CustomerPrivacyRequestRepository(connection)
        self.retention_policies = CustomerDataRetentionPolicyRepository(connection)
        self.audit = CustomerPrivacyAuditRepository(connection)
        self.outbox = CustomerPrivacyOutboxRepository(connection)
        self.processed_events = CustomerPrivacyProcessedEventRepository(connection)
        self._completed = False

    def __enter__(self) -> "CustomerPrivacyUnitOfWork":
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
