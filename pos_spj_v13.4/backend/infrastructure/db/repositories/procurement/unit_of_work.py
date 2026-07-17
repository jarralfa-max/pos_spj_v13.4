"""ProcurementUnitOfWork — one transaction boundary for the procurement context.

Repositories never commit; the UoW commits on clean exit and rolls back on any
exception, guaranteeing atomicity across documents, lines, receipts, audit,
authorization log and outbox. Events enqueued in the outbox are published only
after a successful commit (post-commit dispatch).
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.procurement.direct_purchase_repository import (
    DirectPurchaseRepository,
)
from backend.infrastructure.db.repositories.procurement.goods_receipt_repository import (
    GoodsReceiptRepository,
)
from backend.infrastructure.db.repositories.procurement.purchase_limit_repository import (
    PurchaseLimitRepository,
)
from backend.infrastructure.db.repositories.procurement.support_repositories import (
    DocumentSequenceRepository,
    ProcurementAuditRepository,
    ProcurementOutboxRepository,
    ProcurementProcessedEventRepository,
    PurchaseAuthorizationLogRepository,
)


class ProcurementUnitOfWork:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.direct_purchases = DirectPurchaseRepository(connection)
        self.receipts = GoodsReceiptRepository(connection)
        self.limits = PurchaseLimitRepository(connection)
        self.sequences = DocumentSequenceRepository(connection)
        self.authorization_log = PurchaseAuthorizationLogRepository(connection)
        self.audit = ProcurementAuditRepository(connection)
        self.outbox = ProcurementOutboxRepository(connection)
        self.processed_events = ProcurementProcessedEventRepository(connection)
        self._completed = False

    def __enter__(self) -> "ProcurementUnitOfWork":
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
