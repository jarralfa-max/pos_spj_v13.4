# core/events/domain_events.py — SPJ ERP v13.6
"""
Constantes canónicas de eventos de dominio para el plano ERP.

Reglas:
  - Eventos normalizados según auditoría de arquitectura v13.6
  - Todos los eventos en PAST TENSE (hechos consumados)
  - Sin eventos CRUD (PRODUCT_UPDATED, etc.)
  - Sin duplicados (usar alias si hay legacy code)
  
Catálogo oficial:
  Inventario: STOCK_MOVED, STOCK_LEVEL_CRITICAL
  Ventas: SALE_COMPLETED, SALE_CANCELLED
  Producción: PRODUCTION_ORDER_COMPLETED, RECIPE_DEVIATION_DETECTED
  Compras: PURCHASE_ORDER_RECEIVED, ACCOUNT_PAYABLE_CREATED
  Finanzas: PAYMENT_REGISTERED, ACCOUNT_RECEIVABLE_CREATED
  Lealtad: LOYALTY_POINTS_ACCUMULATED, LOYALTY_POINTS_REDEEMED, CUSTOMER_TIER_CHANGED
  Residuos: WASTE_RECORDED
  Cotizaciones: QUOTE_CONVERTED, QUOTE_EXPIRED
"""
from core.events.event_bus import (
    # Ventas - aliases a eventos legacy
    VENTA_COMPLETADA        as SALE_COMPLETED,     # "VENTA_COMPLETADA"
    VENTA_CANCELADA         as SALE_CANCELLED,     # "VENTA_CANCELADA"
    
    # Compras - aliases
    COMPRA_REGISTRADA       as PURCHASE_ORDER_RECEIVED,  # Legacy: "COMPRA_REGISTRADA"
    
    # Producción - aliases
    PRODUCCION_COMPLETADA   as PRODUCTION_ORDER_COMPLETED,  # Legacy: "PRODUCCION_COMPLETADA"
    
    # Inventario - aliases
    AJUSTE_INVENTARIO       as STOCK_UPDATED,       # Legacy: "AJUSTE_INVENTARIO"
    TRANSFERENCIA_STOCK     as STOCK_TRANSFERRED,   # Legacy: "TRANSFERENCIA_STOCK"
    STOCK_BAJO_MINIMO       as STOCK_LEVEL_CRITICAL,  # Alias para threshold breach
    
    # Lealtad - aliases
    PUNTOS_ACUMULADOS       as LOYALTY_POINTS_ACCUMULATED,  # Legacy: "PUNTOS_ACUMULADOS"
    NIVEL_CAMBIADO          as CUSTOMER_TIER_CHANGED,  # Legacy: "NIVEL_CAMBIADO"
    
    # Merma - aliases
    MERMA_CREATED           as WASTE_RECORDED,      # Legacy: "MERMA_CREATED"
)

# Eventos nuevos explícitos (ya definidos en event_bus.py v13.6)
STOCK_MOVED               = "STOCK_MOVED"           # UNIFICA todos los movimientos de inventario
RECIPE_DEVIATION_DETECTED = "RECIPE_DEVIATION_DETECTED"  # Variación en rendimiento de producción
ACCOUNT_RECEIVABLE_CREATED = "ACCOUNT_RECEIVABLE_CREATED"  # CxC de ventas crédito
ACCOUNT_PAYABLE_CREATED   = "ACCOUNT_PAYABLE_CREATED"  # CxP de compras crédito
LOYALTY_POINTS_REDEEMED   = "LOYALTY_POINTS_REDEEMED"  # Redención de puntos
PAYMENT_REGISTERED        = "PAYMENT_REGISTERED"    # Movimiento financiero unificado
QUOTE_CONVERTED           = "QUOTE_CONVERTED"       # Cotización → Venta
QUOTE_EXPIRED             = "QUOTE_EXPIRED"         # Cotización expirada

__all__ = [
    # Ventas
    "SALE_COMPLETED",
    "SALE_CANCELLED",
    
    # Inventario
    "STOCK_MOVED",
    "STOCK_LEVEL_CRITICAL",
    "STOCK_UPDATED",
    "STOCK_TRANSFERRED",
    
    # Producción
    "PRODUCTION_ORDER_COMPLETED",
    "RECIPE_DEVIATION_DETECTED",
    
    # Compras
    "PURCHASE_ORDER_RECEIVED",
    "ACCOUNT_PAYABLE_CREATED",
    
    # Finanzas
    "PAYMENT_REGISTERED",
    "ACCOUNT_RECEIVABLE_CREATED",
    
    # Lealtad
    "LOYALTY_POINTS_ACCUMULATED",
    "LOYALTY_POINTS_REDEEMED",
    "CUSTOMER_TIER_CHANGED",
    
    # Residuos
    "WASTE_RECORDED",
    
    # Cotizaciones
    "QUOTE_CONVERTED",
    "QUOTE_EXPIRED",
]
