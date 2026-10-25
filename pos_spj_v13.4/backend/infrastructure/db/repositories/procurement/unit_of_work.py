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
from backend.infrastructure.db.repositories.procurement.purchase_order_repository import (
    PurchaseOrderRepository,
)
from backend.infrastructure.db.repositories.procurement.purchase_return_repository import (
    PurchaseReturnRepository,
)
from backend.infrastructure.db.repositories.procurement.requisition_repository import (
    PurchaseRequisitionRepository,
)
from backend.infrastructure.db.repositories.procurement.rfq_repository import RfqRepository
from backend.infrastructure.db.repositories.procurement.supplier_invoice_repository import (
    SupplierInvoiceRepository,
)
from backend.infrastructure.db.repositories.procurement.support_repositories import (
    DocumentSequenceRepository,
    ProcurementAuditRepository,
    ProcurementOutboxRepository,
    ProcurementProcessedEventRepository,
    PurchaseAuthorizationLogRepository,
)
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class ProcurementUnitOfWork(TransactionalUnitOfWork):
    """Context manager: commit al salir limpio, rollback ante excepción — sólo
    si es la DUEÑA de la transacción. Anidada dentro de otra (un coordinador que
    compone casos de uso), participa en la del coordinador; con
    ``owns_transaction=False`` participa en la de otro contexto (p. ej. Ventas)."""

    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
        self.direct_purchases = DirectPurchaseRepository(connection)
        self.requisitions = PurchaseRequisitionRepository(connection)
        self.orders = PurchaseOrderRepository(connection)
        self.rfqs = RfqRepository(connection)
        self.invoices = SupplierInvoiceRepository(connection)
        self.receipts = GoodsReceiptRepository(connection)
        self.returns = PurchaseReturnRepository(connection)
        self.limits = PurchaseLimitRepository(connection)
        self.sequences = DocumentSequenceRepository(connection)
        self.authorization_log = PurchaseAuthorizationLogRepository(connection)
        self.audit = ProcurementAuditRepository(connection)
        self.outbox = ProcurementOutboxRepository(connection)
        self.processed_events = ProcurementProcessedEventRepository(connection)
        self._completed = False
