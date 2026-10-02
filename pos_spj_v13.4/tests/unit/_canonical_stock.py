"""Existencia canónica para las pruebas de Ventas que suspenden o cobran.

Suspender y cobrar reservan inventario por el modelo CANÓNICO
(`inventory_balances` + `inventory_reservation`). Varias pruebas montaban a mano
las tablas legacy `stock_reservas`/`inventory_stock` y dejaron de servir el día
que Ventas pasó a la vía canónica (re-auditoría POS, 2026-10-01): un solo sitio
para sembrar existencia en vez de una copia del DDL por archivo.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.inventory.authorization import (
    AllowAllInventoryPermissionCheckerForTests,
    InventoryAuthorizationPolicy,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


def allow_all_inventory() -> InventoryAuthorizationPolicy:
    return InventoryAuthorizationPolicy(AllowAllInventoryPermissionCheckerForTests())


def create_canonical_inventory(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()


def seed_available_stock(conn, *, branch_id: str, product_id: str, quantity="999") -> None:
    """Existencia disponible sin lote, en el almacén por omisión de la
    sucursal (la sucursal misma), que es donde reserva Ventas sin almacenes."""
    from backend.domain.inventory.entities.inventory_balance import InventoryBalance
    from backend.domain.inventory.enums import InventoryStatus
    from backend.infrastructure.db.repositories.inventory.unit_of_work import InventoryUnitOfWork

    with InventoryUnitOfWork(conn) as uow:
        balance = InventoryBalance.empty(
            product_id=product_id, branch_id=branch_id, warehouse_id=branch_id,
            inventory_status=InventoryStatus.AVAILABLE, location_id=branch_id)
        balance.apply_delta(quantity=Decimal(str(quantity)))
        uow.balances.upsert(balance)
    conn.commit()
