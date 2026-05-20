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
    VENTA_CANCELADA,                              # "VENTA_CANCELADA"
    PUNTOS_ACUMULADOS,                            # "PUNTOS_ACUMULADOS"
    NIVEL_CAMBIADO,                               # "NIVEL_CAMBIADO"
)

# Nuevos eventos ERP (lowercase — no existen en event_bus.py)
INVENTORY_MOVEMENT  = "inventory_movement"   # emitido por UnifiedInventoryService.process_movement()
PAYMENT_RECEIVED    = "payment_received"     # emitido por UnifiedThirdPartyService.apply_payment()
EXPENSE_REGISTERED  = "expense_registered"   # emitido al registrar gasto/CXP

# Phase 1: internal sync event — inventory + finance handlers run inside SAVEPOINT.
# Distinct from VENTA_COMPLETADA (async, post-commit, for downstream consumers).
SALE_ITEMS_PROCESS  = "sale_items_process"

# Phase 3: internal sync event — inventory handler runs inside production transaction.
# Distinct from PRODUCCION_COMPLETADA (async, post-commit, for downstream consumers).
PRODUCTION_ITEMS_PROCESS = "production_items_process"

# Phase 4: internal sync event — inventory handler runs inside purchase SAVEPOINT.
# Distinct from COMPRA_REGISTRADA (async, post-commit, for downstream consumers).
PURCHASE_ITEMS_PROCESS = "purchase_items_process"

# Phase 5: inter-branch transfer events.
# TRANSFER_CREATED / TRANSFER_COMPLETED alias the existing bus constants so
# downstream consumers can use ERP-standard names without changing the bus channel.
from core.events.event_bus import (
    TRASPASO_INICIADO   as TRANSFER_CREATED,    # "TRASPASO_INICIADO"
    TRASPASO_CONFIRMADO as TRANSFER_COMPLETED,  # "TRASPASO_CONFIRMADO"
)
# Internal sync event — inventory handler runs inside transfer SAVEPOINT.
TRANSFER_ITEMS_PROCESS = "transfer_items_process"

# Reserva de stock (ventas suspendidas / pedidos anticipados).
# No existen en event_bus.py — son eventos de UI/orquestación, sin handlers críticos.
VENTA_SUSPENDIDA          = "venta_suspendida"
STOCK_RESERVADO           = "stock_reservado"
VENTA_CONFIRMADA_RESERVA  = "venta_confirmada"           # confirma reserva previa
STOCK_DESCONTADO_RESERVA  = "stock_descontado"           # stock de reserva confirmado
STOCK_ACTUALIZADO         = "stock_actualizado"          # refresco visual post-venta
VENTA_SUSPENDIDA_CANCELADA = "venta_suspendida_cancelada"
STOCK_RESERVA_LIBERADA    = "stock_reserva_liberada"

__all__ = [
    "SALE_CREATED",
    "PURCHASE_CREATED",
    "PRODUCTION_EXECUTED",
    "STOCK_UPDATED",
    "INVENTORY_MOVEMENT",
    "PAYMENT_RECEIVED",
    "EXPENSE_REGISTERED",
    "SALE_ITEMS_PROCESS",
    "PRODUCTION_ITEMS_PROCESS",
    "PURCHASE_ITEMS_PROCESS",
    "TRANSFER_CREATED",
    "TRANSFER_COMPLETED",
    "TRANSFER_ITEMS_PROCESS",
    "VENTA_CANCELADA",
    "PUNTOS_ACUMULADOS",
    "NIVEL_CAMBIADO",
    "VENTA_SUSPENDIDA",
    "STOCK_RESERVADO",
    "VENTA_CONFIRMADA_RESERVA",
    "STOCK_DESCONTADO_RESERVA",
    "STOCK_ACTUALIZADO",
    "VENTA_SUSPENDIDA_CANCELADA",
    "STOCK_RESERVA_LIBERADA",
]

