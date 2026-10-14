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


#: Profundidad de unidades de trabajo de Compras abiertas por conexión
#: (auditoría C20). Sólo la más externa confirma o revierte: una interna que
#: hiciera commit confirmaría también lo que el coordinador aún podría revertir.
#: Guarda la conexión misma (no sólo su id): mientras la entrada exista la
#: conexión sigue viva y ninguna otra puede heredar su id.
_OPEN_DEPTH: dict[int, tuple[Any, int]] = {}


class ProcurementUnitOfWork:
    """Context manager: commit al salir limpio, rollback ante excepción — sólo
    si es la DUEÑA de la transacción. Anidada dentro de otra (un coordinador que
    compone casos de uso), participa en la del coordinador; con
    ``owns_transaction=False`` participa en la de otro contexto (p. ej. Ventas)."""

    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._requested_ownership = owns_transaction
        self._owner = owns_transaction
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

    def __enter__(self) -> "ProcurementUnitOfWork":
        self._completed = False
        key = id(self.connection)
        holder, depth = _OPEN_DEPTH.get(key, (self.connection, 0))
        if holder is not self.connection:   # id reutilizado: entrada huérfana
            depth = 0
        self._owner = self._requested_ownership and depth == 0
        _OPEN_DEPTH[key] = (self.connection, depth + 1)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        try:
            if exc_type is not None:
                self.rollback()
            elif not self._completed:
                self.commit()
        finally:
            key = id(self.connection)
            holder, depth = _OPEN_DEPTH.get(key, (self.connection, 1))
            if holder is self.connection and depth > 1:
                _OPEN_DEPTH[key] = (holder, depth - 1)
            else:
                _OPEN_DEPTH.pop(key, None)
        return False

    def commit(self) -> None:
        if self._owner:
            self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        if self._owner:
            rollback = getattr(self.connection, "rollback", None)
            if rollback is not None:
                rollback()
        self._completed = True
