"""CustomerServiceUnitOfWork — one transaction boundary for the Customer
Service (atención al cliente) context. Mirrors
backend/infrastructure/db/repositories/crm/unit_of_work.py.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.customer_service.service_case_category_repository import (
    ServiceCaseCategoryRepository,
)
from backend.infrastructure.db.repositories.customer_service.service_case_escalation_repository import (
    ServiceCaseEscalationRepository,
)
from backend.infrastructure.db.repositories.customer_service.service_case_repository import (
    ServiceCaseRepository,
)
from backend.infrastructure.db.repositories.customer_service.service_case_resolution_repository import (
    ServiceCaseResolutionRepository,
)
from backend.infrastructure.db.repositories.customer_service.service_level_policy_repository import (
    ServiceLevelPolicyRepository,
)
from backend.infrastructure.db.repositories.customer_service.sla_instance_repository import (
    SLAInstanceRepository,
)
from backend.infrastructure.db.repositories.customer_service.support_repositories import (
    CustomerServiceAuditRepository,
    CustomerServiceOutboxRepository,
    CustomerServiceProcessedEventRepository,
)


class CustomerServiceUnitOfWork:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.cases = ServiceCaseRepository(connection)
        self.categories = ServiceCaseCategoryRepository(connection)
        self.resolutions = ServiceCaseResolutionRepository(connection)
        self.escalations = ServiceCaseEscalationRepository(connection)
        self.policies = ServiceLevelPolicyRepository(connection)
        self.sla_instances = SLAInstanceRepository(connection)
        self.audit = CustomerServiceAuditRepository(connection)
        self.outbox = CustomerServiceOutboxRepository(connection)
        self.processed_events = CustomerServiceProcessedEventRepository(connection)
        self._completed = False

    def __enter__(self) -> "CustomerServiceUnitOfWork":
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
