"""SupplierUnitOfWork — one transaction boundary for the suppliers context.

Repositories never commit; the UoW commits on clean exit and rolls back on
exception, guaranteeing atomicity across master, children, audit and outbox.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.suppliers.supplier_child_repositories import (
    SupplierAddressRepository,
    SupplierBankAccountRepository,
    SupplierBranchAuthorizationRepository,
    SupplierCommercialTermsRepository,
    SupplierContactRepository,
    SupplierDocumentRepository,
    SupplierProductRepository,
)
from backend.infrastructure.db.repositories.suppliers.supplier_evaluation_repository import (
    SupplierEvaluationRepository,
)
from backend.infrastructure.db.repositories.suppliers.supplier_repository import (
    SupplierRepository,
)
from backend.infrastructure.db.repositories.suppliers.support_repositories import (
    SupplierAuditRepository,
    SupplierOutboxRepository,
    SupplierProcessedEventRepository,
)
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class SupplierUnitOfWork(TransactionalUnitOfWork):
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.suppliers = SupplierRepository(connection)
        self.contacts = SupplierContactRepository(connection)
        self.addresses = SupplierAddressRepository(connection)
        self.bank_accounts = SupplierBankAccountRepository(connection)
        self.terms = SupplierCommercialTermsRepository(connection)
        self.products = SupplierProductRepository(connection)
        self.documents = SupplierDocumentRepository(connection)
        self.branches = SupplierBranchAuthorizationRepository(connection)
        self.evaluations = SupplierEvaluationRepository(connection)
        self.audit = SupplierAuditRepository(connection)
        self.outbox = SupplierOutboxRepository(connection)
        self.processed_events = SupplierProcessedEventRepository(connection)
        self._completed = False
