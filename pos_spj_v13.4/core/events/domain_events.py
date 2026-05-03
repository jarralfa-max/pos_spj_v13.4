# core/events/domain_events.py — SPJ ERP v13.4
"""
Constantes canónicas de eventos de dominio para el plano ERP.

Reglas:
  - Aliases a eventos existentes usan el mismo string que event_bus.py
    (mismo canal EventBus, sin duplicar registros).
  - Eventos NUEVOS usan lowercase para distinguirlos de los legacy UPPERCASE.
  - Dependencia unidireccional: este módulo importa de event_bus, nunca al revés.
"""
from core.events.event_bus import (
    VENTA_COMPLETADA      as SALE_CREATED,       # "VENTA_COMPLETADA"
    COMPRA_REGISTRADA     as PURCHASE_CREATED,   # "COMPRA_REGISTRADA"
    PRODUCCION_COMPLETADA as PRODUCTION_EXECUTED, # "PRODUCCION_COMPLETADA"
    AJUSTE_INVENTARIO     as STOCK_UPDATED,       # "AJUSTE_INVENTARIO"
)

# Nuevos eventos ERP (lowercase — no existen en event_bus.py)
INVENTORY_MOVEMENT  = "inventory_movement"   # emitido por UnifiedInventoryService.process_movement()
PAYMENT_RECEIVED    = "payment_received"     # emitido por UnifiedThirdPartyService.apply_payment()
EXPENSE_REGISTERED  = "expense_registered"   # emitido al registrar gasto/CXP

__all__ = [
    "SALE_CREATED",
    "PURCHASE_CREATED",
    "PRODUCTION_EXECUTED",
    "STOCK_UPDATED",
    "INVENTORY_MOVEMENT",
    "PAYMENT_RECEIVED",
    "EXPENSE_REGISTERED",
]
