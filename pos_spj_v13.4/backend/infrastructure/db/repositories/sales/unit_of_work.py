"""SalesUnitOfWork — one transaction boundary for the Sales/POS context.
Mirrors backend/infrastructure/db/repositories/inventory/unit_of_work.py's
`InventoryUnitOfWork` exactly (same `owns_transaction` flag, same
`__enter__`/`__exit__` shape) — chosen over Cash Register's simpler
no-flag version because a real POS checkout will need to compose Sales +
Inventory + Cash writes inside one outer SAVEPOINT, exactly the scenario
Inventory's own docstring names.

Repositories never commit; this UoW commits on clean exit and rolls back on
any exception, guaranteeing atomicity across a Sale, its lines, and any
outbox event enqueued in the same transaction.

When ``owns_transaction=False`` the UoW writes on a connection whose
transaction boundary is owned by an *outer* flow — ``commit()``/
``rollback()`` become no-ops on the connection (only ``self._completed`` is
tracked), letting that outer flow decide the real commit/rollback point.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.sales.outbox_repository import SalesOutboxRepository
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository


class SalesUnitOfWork:
    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
        self.sales = SaleRepository(connection)
        self.outbox = SalesOutboxRepository(connection)
        self._completed = False

    def __enter__(self) -> "SalesUnitOfWork":
        self._completed = False
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        elif not self._completed:
            self.commit()
        return False

    def commit(self) -> None:
        if self._owns_transaction:
            self.connection.commit()
        self._completed = True

    def rollback(self) -> None:
        if self._owns_transaction:
            rollback = getattr(self.connection, "rollback", None)
            if rollback is not None:
                rollback()
        self._completed = True
