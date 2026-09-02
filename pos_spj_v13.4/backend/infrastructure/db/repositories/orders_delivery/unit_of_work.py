"""OrdersDeliveryUnitOfWork — one transaction boundary for the Pedidos/
Delivery context. Mirrors
backend/infrastructure/db/repositories/sales/unit_of_work.py's
`SalesUnitOfWork` exactly.

Repositories never commit; this UoW commits on clean exit and rolls back on
any exception, guaranteeing atomicity across a CustomerOrder, its lines, and
any outbox event enqueued in the same transaction.
"""

from __future__ import annotations

from typing import Any

from backend.infrastructure.db.repositories.orders_delivery.address_repository import (
    OrderAddressRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.cash_collection_repository import (
    DriverCashCollectionRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_zone_repository import (
    DeliveryZoneRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.driver_repository import (
    DeliveryAssignmentRepository,
    DriverOperationalProfileRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.outbox_repository import (
    OrdersDeliveryOutboxRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.package_repository import (
    OrderPackageRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.redelivery_repository import (
    RedeliveryRequestRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.route_repository import (
    DeliveryRouteRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.settlement_repository import (
    DriverSettlementRepository,
)


class OrdersDeliveryUnitOfWork:
    def __init__(self, connection: Any, *, owns_transaction: bool = True) -> None:
        self.connection = connection
        self._owns_transaction = owns_transaction
        self.orders = CustomerOrderRepository(connection)
        self.addresses = OrderAddressRepository(connection)
        self.zones = DeliveryZoneRepository(connection)
        self.packages = OrderPackageRepository(connection)
        self.delivery_jobs = DeliveryJobRepository(connection)
        self.driver_profiles = DriverOperationalProfileRepository(connection)
        self.assignments = DeliveryAssignmentRepository(connection)
        self.routes = DeliveryRouteRepository(connection)
        self.redeliveries = RedeliveryRequestRepository(connection)
        self.cash_collections = DriverCashCollectionRepository(connection)
        self.settlements = DriverSettlementRepository(connection)
        self.outbox = OrdersDeliveryOutboxRepository(connection)
        self._completed = False

    def __enter__(self) -> "OrdersDeliveryUnitOfWork":
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
