"""CRMUnitOfWork — one transaction boundary for the CRM (relationship)
context. Mirrors
backend/infrastructure/db/repositories/customers/unit_of_work.py.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.crm.activity_repository import CRMActivityRepository
from backend.infrastructure.db.repositories.crm.lead_qualification_repository import (
    LeadQualificationRepository,
)
from backend.infrastructure.db.repositories.crm.lead_repository import LeadRepository
from backend.infrastructure.db.repositories.crm.note_repository import CRMNoteRepository
from backend.infrastructure.db.repositories.crm.opportunity_repository import (
    OpportunityRepository,
)
from backend.infrastructure.db.repositories.crm.product_interest_repository import (
    OpportunityProductInterestRepository,
)
from backend.infrastructure.db.repositories.crm.reminder_repository import CRMReminderRepository
from backend.infrastructure.db.repositories.crm.stage_definition_repository import (
    CRMStageDefinitionRepository,
)
from backend.infrastructure.db.repositories.crm.stage_history_repository import (
    OpportunityStageHistoryRepository,
)
from backend.infrastructure.db.repositories.crm.support_repositories import (
    CRMAuditRepository,
    CRMOutboxRepository,
    CRMProcessedEventRepository,
)
from backend.infrastructure.db.repositories.crm.task_repository import CRMTaskRepository


class CRMUnitOfWork:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.leads = LeadRepository(connection)
        self.qualifications = LeadQualificationRepository(connection)
        self.opportunities = OpportunityRepository(connection)
        self.stage_definitions = CRMStageDefinitionRepository(connection)
        self.stage_history = OpportunityStageHistoryRepository(connection)
        self.product_interests = OpportunityProductInterestRepository(connection)
        self.activities = CRMActivityRepository(connection)
        self.tasks = CRMTaskRepository(connection)
        self.notes = CRMNoteRepository(connection)
        self.reminders = CRMReminderRepository(connection)
        self.audit = CRMAuditRepository(connection)
        self.outbox = CRMOutboxRepository(connection)
        self.processed_events = CRMProcessedEventRepository(connection)
        self._completed = False

    def __enter__(self) -> "CRMUnitOfWork":
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
