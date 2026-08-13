"""One atomic transaction for all Cash Register state and messages."""
from __future__ import annotations

from typing import Any

from .repositories import (
    CashAuditRepository, CashCountRepository, CashCutRepository, CashDeviceRepository, CashDifferenceRepository,
    CashDifferencePolicyRepository, CashDrawerEventRepository,
    CashDepositPreparationRepository, CashEventRepository, CashHandoverRepository,
    CashIdempotencyRepository, CashLedgerRepository, CashMovementReasonRepository,
    CashOutboxRepository, CashSettlementRepository, CashShiftRepository, CashSyncRepository,
)
from .configuration_repository import CashConfigurationWriteRepository
from .notification_repository import CashNotificationRepository
from .printing_repository import CashPrintRepository


class CashRegisterUnitOfWork:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
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
        self.differences = CashDifferenceRepository(connection)
        self.difference_policies = CashDifferencePolicyRepository(connection)
        self.events = CashEventRepository(connection)
        self.outbox = CashOutboxRepository(connection)
        self.sync = CashSyncRepository(connection)
        self.notifications = CashNotificationRepository(connection)
        self.printing = CashPrintRepository(connection)
        self.audit = CashAuditRepository(connection)
        self._completed = False

    def __enter__(self) -> "CashRegisterUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        if self._completed:
            raise RuntimeError("Cash Register UnitOfWork already completed")
        self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        if self._completed:
            return
        self.connection.rollback()
        self._completed = True
