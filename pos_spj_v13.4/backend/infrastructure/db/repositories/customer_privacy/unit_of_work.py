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
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class CustomerPrivacyUnitOfWork(TransactionalUnitOfWork):
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
