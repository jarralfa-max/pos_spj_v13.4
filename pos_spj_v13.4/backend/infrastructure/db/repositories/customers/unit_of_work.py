"""CustomerUnitOfWork — one transaction boundary for the Customer Master
context. Repositories never commit; the UoW commits on clean exit and rolls
back on exception, guaranteeing atomicity across master, children, audit and
outbox. Mirrors
backend/infrastructure/db/repositories/suppliers/unit_of_work.py.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.customers.customer_child_repositories import (
    CustomerAccountRepository,
    CustomerAddressRepository,
    CustomerContactRepository,
    CustomerTaxProfileRepository,
)
from backend.infrastructure.db.repositories.customers.customer_data_quality_issue_repository import (
    CustomerDataQualityIssueRepository,
)
from backend.infrastructure.db.repositories.customers.customer_duplicate_candidate_repository import (
    CustomerDuplicateCandidateRepository,
)
from backend.infrastructure.db.repositories.customers.customer_import_batch_repository import (
    CustomerImportBatchRepository,
)
from backend.infrastructure.db.repositories.customers.customer_merge_record_repository import (
    CustomerMergeRecordRepository,
)
from backend.infrastructure.db.repositories.customers.customer_repository import (
    CustomerRepository,
)
from backend.infrastructure.db.repositories.customers.support_repositories import (
    CustomerAuditRepository,
    CustomerOutboxRepository,
    CustomerProcessedEventRepository,
)
from backend.infrastructure.db.repositories.customers.customer_sync_conflict_repository import (
    CustomerSyncConflictRepository,
)


class CustomerUnitOfWork:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.customers = CustomerRepository(connection)
        self.accounts = CustomerAccountRepository(connection)
        self.contacts = CustomerContactRepository(connection)
        self.addresses = CustomerAddressRepository(connection)
        self.tax_profiles = CustomerTaxProfileRepository(connection)
        self.duplicate_candidates = CustomerDuplicateCandidateRepository(connection)
        self.merge_records = CustomerMergeRecordRepository(connection)
        self.data_quality_issues = CustomerDataQualityIssueRepository(connection)
        self.import_batches = CustomerImportBatchRepository(connection)
        self.sync_conflicts = CustomerSyncConflictRepository(connection)
        self.audit = CustomerAuditRepository(connection)
        self.outbox = CustomerOutboxRepository(connection)
        self.processed_events = CustomerProcessedEventRepository(connection)
        self._completed = False

    def __enter__(self) -> "CustomerUnitOfWork":
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
