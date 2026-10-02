"""Reserva de existencia para una venta (Inventario decide de qué lote sale).

POR QUÉ EXISTE (POS re-auditoría, 2026-10-01)
---------------------------------------------
Ventas reservaba con `CreateReservationUseCase`, que retiene UN saldo concreto
buscado SIN lote (`lot_id=None`). Pero Compras recibe SIEMPRE con lote — aunque
el producto no sea "controlado por lote", la recepción crea uno para la
trazabilidad. Medido en una copia de la base real: los 23 kg de Alas viven en
un saldo con lote, así que la reserva respondía "Sin balance disponible para
reservar" y **no se podía cobrar nada que hubiera entrado por Compras**; la
venta quedaba atorada en cobro con el pago ya registrado. Y como ese fallo no
era una "falta de existencia", ni siquiera ofrecía la autorización para vender
sin existencia.

Producción ya resolvía exactamente esto (`ReserveStockForProductionUseCase`:
Inventario elige los saldos con la estrategia configurada y reserva cada saldo
EXACTO, lote y ubicación incluidos, todo o nada). Ventas lo hereda cambiando
sólo lo que distingue a una venta, en vez de tener una segunda manera de
reservar por lotes:

- origen `SALE`;
- estrategia en `inventory_settings` con la clave `sales.allocation_strategy`
  (almacén → sucursal → global; sin configurar, FEFO);
- admite lotes en inspección (`PENDING_INSPECTION`), igual que la política por
  omisión del dominio: el mostrador vende lo recibido hoy. Lotes bloqueados,
  en cuarentena, rechazados o caducados no se venden nunca.

`plan_sale_issue` es la otra mitad: cuando no alcanza y otro usuario autorizó
vender sin existencia, lo que SÍ hay sale de sus lotes y sólo el faltante va a
negativo — antes se descontaba todo de un saldo sin lote y el lote real se
quedaba intacto, contado dos veces.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.inventory.use_cases.production_reservation_use_cases import (
    ReserveStockForProductionUseCase,
    configured_strategy,
)
from backend.domain.inventory.enums import ReservationSource
from backend.domain.inventory.services.lot_allocation_service import (
    LotAllocation,
    LotAllocationService,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import InventoryUnitOfWork

SALES_STRATEGY_SETTING = "sales.allocation_strategy"


class ReserveStockForSaleUseCase(ReserveStockForProductionUseCase):
    _SOURCE = ReservationSource.SALE
    _STRATEGY_SETTING = SALES_STRATEGY_SETTING
    _PURPOSE = "venta"
    _REQUIRE_RELEASED = False


def plan_sale_issue(connection, *, product_id: str, branch_id: str, warehouse_id: str,
                    quantity: Decimal) -> tuple[list[LotAllocation], Decimal]:
    """Qué saldos cubren `quantity` (misma estrategia y elegibilidad que la
    reserva) y cuánto falta. No escribe nada: es el plan de una salida que el
    llamador ya autorizó a quedar en negativo por el faltante."""
    uow = InventoryUnitOfWork(connection)
    strategy = configured_strategy(uow, branch_id=branch_id, warehouse_id=warehouse_id,
                                   setting_key=SALES_STRATEGY_SETTING)
    candidatos = ReserveStockForSaleUseCase._candidates(
        uow, product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
        lot_required=False)
    return LotAllocationService().allocate_partial(
        candidatos, Decimal(str(quantity)), strategy=strategy,
        require_released=ReserveStockForSaleUseCase._REQUIRE_RELEASED)
