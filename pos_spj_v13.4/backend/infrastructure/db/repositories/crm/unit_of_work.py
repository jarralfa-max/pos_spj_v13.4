"""CRMUnitOfWork — one transaction boundary for the CRM (relationship)
context. Mirrors
backend/infrastructure/db/repositories/customers/unit_of_work.py.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.crm.activity_repository import CRMActivityRepository
from backend.infrastructure.db.repositories.crm.automation_repository import (
    CRMAutomationExecutionRepository,
    CRMAutomationRuleRepository,
)
from backend.infrastructure.db.repositories.crm.customer_ownership_repository import (
    CustomerOwnershipRepository,
)
from backend.infrastructure.db.repositories.crm.customer_portfolio_repository import (
    CustomerPortfolioRepository,
)
from backend.infrastructure.db.repositories.crm.customer_segment_membership_repository import (
    CustomerSegmentMembershipRepository,
)
from backend.infrastructure.db.repositories.crm.customer_segment_repository import (
    CustomerSegmentRepository,
)
from backend.infrastructure.db.repositories.crm.customer_tag_assignment_repository import (
    CustomerTagAssignmentRepository,
)
from backend.infrastructure.db.repositories.crm.customer_tag_repository import (
    CustomerTagRepository,
)
from backend.infrastructure.db.repositories.crm.crm_sync_conflict_repository import (
    CRMSyncConflictRepository,
)
from backend.infrastructure.db.repositories.crm.lead_qualification_repository import (
    LeadQualificationRepository,
)
from backend.infrastructure.db.repositories.crm.lead_repository import LeadRepository
from backend.infrastructure.db.repositories.crm.note_repository import CRMNoteRepository
from backend.infrastructure.db.repositories.crm.opportunity_repository import (
    OpportunityRepository,
)
from backend.infrastructure.db.repositories.crm.portfolio_assignment_repository import (
    PortfolioAssignmentRepository,
)
from backend.infrastructure.db.repositories.crm.product_interest_repository import (
    OpportunityProductInterestRepository,
)
from backend.infrastructure.db.repositories.crm.reminder_repository import CRMReminderRepository
from backend.infrastructure.db.repositories.crm.sales_territory_repository import (
    SalesTerritoryRepository,
)
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
        self.territories = SalesTerritoryRepository(connection)
        self.portfolios = CustomerPortfolioRepository(connection)
        self.ownerships = CustomerOwnershipRepository(connection)
        self.portfolio_assignments = PortfolioAssignmentRepository(connection)
        self.segments = CustomerSegmentRepository(connection)
        self.segment_memberships = CustomerSegmentMembershipRepository(connection)
        self.tags = CustomerTagRepository(connection)
        self.tag_assignments = CustomerTagAssignmentRepository(connection)
        self.automation_rules = CRMAutomationRuleRepository(connection)
        self.automation_executions = CRMAutomationExecutionRepository(connection)
        self.sync_conflicts = CRMSyncConflictRepository(connection)
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
