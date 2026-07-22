"""InventoryUnitOfWork — one transaction boundary for the inventory context.

Repositories never commit; the UoW commits on clean exit and rolls back on any
exception, guaranteeing atomicity across the ledger movement, its lines, the
balance projection, the authorization/audit log and the outbox (§4). Events
enqueued in the outbox are published only after a successful commit.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.inventory.adjustment_repository import (
    AdjustmentRepository,
)
from backend.infrastructure.db.repositories.inventory.cold_chain_repository import (
    ColdChainRepository,
)
from backend.infrastructure.db.repositories.inventory.count_repository import (
    CountRepository,
)
from backend.infrastructure.db.repositories.inventory.quarantine_repository import (
    QuarantineRepository,
)
from backend.infrastructure.db.repositories.inventory.inventory_balance_repository import (
    InventoryBalanceRepository,
)
from backend.infrastructure.db.repositories.inventory.inventory_ledger_repository import (
    InventoryLedgerRepository,
)
from backend.infrastructure.db.repositories.inventory.inventory_limit_repository import (
    InventoryLimitRepository,
)
from backend.infrastructure.db.repositories.inventory.inventory_lot_repository import (
    InventoryLotRepository,
)
from backend.infrastructure.db.repositories.inventory.replenishment_repository import (
    ReplenishmentRuleRepository,
    ReplenishmentSuggestionRepository,
)
from backend.infrastructure.db.repositories.inventory.reservation_repository import (
    ReservationRepository,
)
from backend.infrastructure.db.repositories.inventory.traceability_repository import (
    TraceabilityRepository,
)
from backend.infrastructure.db.repositories.inventory.transfer_repository import (
    TransferRepository,
)
from backend.infrastructure.db.repositories.inventory.waste_repository import (
    WasteRepository,
)
from backend.infrastructure.db.repositories.inventory.support_repositories import (
    InventoryAuditRepository,
    InventoryAuthorizationLogRepository,
    InventoryOutboxRepository,
    InventoryProcessedEventRepository,
    InventorySettingsRepository,
)
from backend.infrastructure.db.repositories.inventory.warehouse_repository import (
    WarehouseRepository,
)


class InventoryUnitOfWork:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.ledger = InventoryLedgerRepository(connection)
        self.balances = InventoryBalanceRepository(connection)
        self.lots = InventoryLotRepository(connection)
        self.reservations = ReservationRepository(connection)
        self.transfers = TransferRepository(connection)
        self.counts = CountRepository(connection)
        self.adjustments = AdjustmentRepository(connection)
        self.quarantines = QuarantineRepository(connection)
        self.waste = WasteRepository(connection)
        self.traceability = TraceabilityRepository(connection)
        self.replenishment_rules = ReplenishmentRuleRepository(connection)
        self.replenishment_suggestions = ReplenishmentSuggestionRepository(connection)
        self.cold_chain = ColdChainRepository(connection)
        self.warehouses = WarehouseRepository(connection)
        self.limits = InventoryLimitRepository(connection)
        self.settings = InventorySettingsRepository(connection)
        self.authorization_log = InventoryAuthorizationLogRepository(connection)
        self.audit = InventoryAuditRepository(connection)
        self.outbox = InventoryOutboxRepository(connection)
        self.processed_events = InventoryProcessedEventRepository(connection)
        self._completed = False

    def __enter__(self) -> "InventoryUnitOfWork":
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
