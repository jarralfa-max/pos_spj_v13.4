"""One atomic transaction for all Cash Register state and messages."""
from __future__ import annotations

from typing import Any

from .repositories import (
    CashAuditRepository, CashCountRepository, CashCutRepository, CashDeviceRepository, CashDifferenceRepository,
    CashDifferencePolicyRepository, CashDrawerEventRepository,
    CashDepositPreparationRepository, CashEventRepository, CashHandoverRepository,
    CashIdempotencyRepository, CashLedgerRepository, CashMovementReasonRepository,
    CashOutboxRepository, CashSettlementRepository, CashShiftRepository,
)
from .configuration_repository import CashConfigurationWriteRepository
from .folio_repository import CashDocumentFolioRepository
from .notification_repository import CashNotificationRepository
from .printing_repository import CashPrintRepository
from backend.infrastructure.db.transaction import TransactionalUnitOfWork


class CashRegisterUnitOfWork(TransactionalUnitOfWork):
    _reject_double_commit = True

    """``owns_transaction=False`` (auditoría de Ventas V06, 2026-10-15): Caja se
    compone dentro de la transacción de quien la llama — el cobro o la
    devolución de Ventas — en vez de confirmar por su cuenta. Así el efectivo
    de una venta y la venta misma viven o mueren juntos: antes Caja corría
    DESPUÉS del commit de la venta y un fallo sólo quedaba en el log."""

    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
        self.shifts = CashShiftRepository(connection)
        self.devices = CashDeviceRepository(connection)
        self.ledger = CashLedgerRepository(connection)
        self.settlements = CashSettlementRepository(connection)
        self.drawer_events = CashDrawerEventRepository(connection)
        self.deposit_preparations = CashDepositPreparationRepository(connection)
        self.configuration = CashConfigurationWriteRepository(connection)
        self.movement_reasons = CashMovementReasonRepository(connection)
        self.handovers = CashHandoverRepository(connection)
        self.idempotency = CashIdempotencyRepository(connection)
        self.counts = CashCountRepository(connection)
        self.cuts = CashCutRepository(connection)
        self.folios = CashDocumentFolioRepository(connection)
        self.differences = CashDifferenceRepository(connection)
        self.difference_policies = CashDifferencePolicyRepository(connection)
        self.events = CashEventRepository(connection)
        self.outbox = CashOutboxRepository(connection)
        self.notifications = CashNotificationRepository(connection)
        self.printing = CashPrintRepository(connection)
        self.audit = CashAuditRepository(connection)
        self._completed = False
