"""InventoryUnitOfWork — one transaction boundary for the inventory context.

Repositories never commit; the UoW commits on clean exit and rolls back on any
exception, guaranteeing atomicity across the ledger movement, its lines, the
balance projection, the authorization/audit log and the outbox (§4). Events
enqueued in the outbox are published only after a successful commit.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.inventory.inventory_balance_repository import (
    InventoryBalanceRepository,
)
from backend.infrastructure.db.repositories.inventory.inventory_ledger_repository import (
    InventoryLedgerRepository,
)
from backend.infrastructure.db.repositories.inventory.inventory_limit_repository import (
    InventoryLimitRepository,
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
