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

# Batch-based production (ProductionEngine.close_batch) — published post-commit with
# full cost data from production_cost_ledger.  Finance handler reads the ledger via db=.
PRODUCTION_BATCH_CREATED = "PRODUCTION_BATCH_CREATED"

# Phase 4: internal sync event — inventory handler runs inside purchase SAVEPOINT.
# Distinct from COMPRA_REGISTRADA (async, post-commit, for downstream consumers).
PURCHASE_ITEMS_PROCESS = "purchase_items_process"

# Canonical inter-branch transfer facts.
from core.events.event_bus import (
    TRANSFER_DISPATCHED as TRANSFER_CREATED,
    TRANSFER_RECEIVED as TRANSFER_COMPLETED,
)

# Reserva de stock (ventas suspendidas / pedidos anticipados).
# No existen en event_bus.py — son eventos de UI/orquestación, sin handlers críticos.
VENTA_SUSPENDIDA          = "venta_suspendida"
STOCK_RESERVADO           = "stock_reservado"
VENTA_CONFIRMADA_RESERVA  = "venta_confirmada"           # confirma reserva previa
STOCK_DESCONTADO_RESERVA  = "stock_descontado"           # stock de reserva confirmado
STOCK_ACTUALIZADO         = "stock_actualizado"          # refresco visual post-venta
VENTA_SUSPENDIDA_CANCELADA = "venta_suspendida_cancelada"
STOCK_RESERVA_LIBERADA    = "stock_reserva_liberada"

# ── Eventos financieros canónicos (FASE 7) ────────────────────────────────────
# Aliases en inglés para nuevos handlers; los strings legacy (CXP_CREADA, etc.)
# se mantienen en event_bus.py para backward compatibility.
ACCOUNT_PAYABLE_CREATED        = "CXP_CREADA"          # alias de legacy español
ACCOUNT_PAYABLE_PAID           = "CXP_PAGADA"
ACCOUNT_RECEIVABLE_CREATED     = "CXC_CREADA"          # alias de legacy español
ACCOUNT_RECEIVABLE_COLLECTED   = "CXC_COBRADA"
FINANCIAL_MOVEMENT_REGISTERED  = "MOVIMIENTO_FINANCIERO"
JOURNAL_ENTRY_REGISTERED       = "ASIENTO_REGISTRADO"
PAYROLL_PAID                   = "NOMINA_PAGADA"

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
    "PRODUCTION_BATCH_CREATED",
    "PURCHASE_ITEMS_PROCESS",
    "TRANSFER_CREATED",
    "TRANSFER_COMPLETED",
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
    # Eventos financieros canónicos (FASE 7)
    "ACCOUNT_PAYABLE_CREATED",
    "ACCOUNT_PAYABLE_PAID",
    "ACCOUNT_RECEIVABLE_CREATED",
    "ACCOUNT_RECEIVABLE_COLLECTED",
    "FINANCIAL_MOVEMENT_REGISTERED",
    "JOURNAL_ENTRY_REGISTERED",
    "PAYROLL_PAID",
    # Eventos de trazabilidad financiera end-to-end (migración 083)
    "PAYMENT_CONFIRMED",
    "PAYROLL_GENERATED",
    "WASTE_RECORDED",
    "LOYALTY_POINTS_EARNED",
    "LOYALTY_POINTS_REDEEMED",
    "DELIVERY_PAYMENT_CONFIRMED",
    "DRIVER_SETTLEMENT_CREATED",
    "FIXED_ASSET_PURCHASED",
    "FIXED_ASSET_DEPRECIATED",
    "MAINTENANCE_REGISTERED",
    "MAINTENANCE_PAID",
    "OPERATING_SUPPLY_PURCHASED",
    "FINANCIAL_TRACE_COMPLETED",
    "FINANCIAL_TRACE_FAILED",
]

# ── Eventos de trazabilidad financiera end-to-end (migración 083) ─────────────
PAYMENT_CONFIRMED          = "payment_confirmed"         # cobro CxC o pago CxP confirmado
PAYROLL_GENERATED          = "payroll_generated"         # nómina generada (obligación creada)
WASTE_RECORDED             = "waste_recorded"            # merma registrada
LOYALTY_POINTS_EARNED      = "loyalty_points_earned"     # puntos ganados
LOYALTY_POINTS_REDEEMED    = "loyalty_points_redeemed"   # puntos canjeados
DELIVERY_PAYMENT_CONFIRMED = "delivery_payment_confirmed" # cobro delivery confirmado
DRIVER_SETTLEMENT_CREATED  = "driver_settlement_created" # corte de repartidor
FIXED_ASSET_PURCHASED      = "fixed_asset_purchased"     # activo fijo adquirido
FIXED_ASSET_DEPRECIATED    = "fixed_asset_depreciated"   # depreciación mensual registrada
MAINTENANCE_REGISTERED     = "maintenance_registered"    # mantenimiento registrado
MAINTENANCE_PAID           = "maintenance_paid"          # mantenimiento pagado
OPERATING_SUPPLY_PURCHASED = "operating_supply_purchased" # insumo operativo comprado
FINANCIAL_TRACE_COMPLETED  = "financial_trace_completed" # traza financiera completada OK
FINANCIAL_TRACE_FAILED     = "financial_trace_failed"    # traza financiera falló

# ── Eventos de sesión y sucursal ──────────────────────────────────────────────
# Published POST-COMMIT by MainWindow._propagar_usuario after the config is
# persisted. Payload fields:
#   event_id, operation_id, user_id, previous_branch_id, active_branch_id,
#   active_branch_name, timestamp, source_module
ACTIVE_BRANCH_CHANGED = "active_branch_changed"

# ── Eventos de catálogo de SUCURSALES (ciclo de vida, NO sesión) ─────────────
# ACTIVE_BRANCH_CHANGED = cambio de sucursal activa de la sesión/terminal.
# BRANCHES_CHANGED      = el catálogo de sucursales cambió: refrescar combos,
#                         selectores y listas en caliente (sin reiniciar).
# Emitidos POST-COMMIT por CompanyProfileService (core/events/catalog_events.py).
# Payload: event_id, operation_id, branch_id, branch_name, active,
#          action ("created"|"updated"|"deactivated"), timestamp, source_module.
BRANCH_CREATED      = "branch_created"
BRANCH_UPDATED      = "branch_updated"
BRANCH_DEACTIVATED  = "branch_deactivated"
BRANCHES_CHANGED    = "branches_changed"

# ── Eventos de catálogo de PRODUCTOS ──────────────────────────────────────────
# PRODUCTS_CHANGED es el evento agregado para refrescar inventario, ventas,
# compras, recetas, etiquetas y todo módulo que dependa del catálogo.
# Los canales legacy UPPERCASE (PRODUCTO_CREADO/ACTUALIZADO/ELIMINADO en
# event_bus.py) se siguen emitiendo por compatibilidad.
# Payload: event_id, operation_id, product_id, product_name, active,
#          action ("created"|"updated"|"deactivated"), timestamp, source_module.
PRODUCT_CREATED     = "product_created"
PRODUCT_UPDATED     = "product_updated"
PRODUCT_DEACTIVATED = "product_deactivated"
PRODUCTS_CHANGED    = "products_changed"

__all__ += [
    "ACTIVE_BRANCH_CHANGED",
    "BRANCH_CREATED",
    "BRANCH_UPDATED",
    "BRANCH_DEACTIVATED",
    "BRANCHES_CHANGED",
    "PRODUCT_CREATED",
    "PRODUCT_UPDATED",
    "PRODUCT_DEACTIVATED",
    "PRODUCTS_CHANGED",
]

# ── Eventos de Business Intelligence / Forecasting / Decision Intelligence ───
# BI-2: catálogo canónico para el bounded context de analítica (ver
# docs/refactor/BI-2_security.md). Ninguno de estos existía antes — el único
# evento relacionado en event_bus.py es el legacy FORECAST_GENERADO (Spanish,
# UPPERCASE, payload de core/services/forecast_service.py, huérfano de
# producción — ver BI-0). No se toca ese legacy string aquí; se retira junto
# con su emisor en BI-32. core/forecast/replenishment_engine.py también
# publica un string crudo NO registrado "FORECAST_GENERATED" (inglés) — motor
# muerto (nunca wireado), su reemplazo real usará FORECAST_RUN_COMPLETED.
#
# Payload mínimo común a todos: event_id, operation_id, occurred_at (§122).
ANALYTICS_SNAPSHOT_CREATED       = "analytics_snapshot_created"
FORECAST_RUN_STARTED             = "forecast_run_started"
FORECAST_RUN_COMPLETED           = "forecast_run_completed"
FORECAST_RUN_FAILED              = "forecast_run_failed"
FORECAST_MODEL_APPROVED          = "forecast_model_approved"
FORECAST_MODEL_ACTIVATED         = "forecast_model_activated"
FORECAST_MODEL_DEGRADED          = "forecast_model_degraded"
ANALYTICS_ALERT_CREATED          = "analytics_alert_created"
ANALYTICS_ALERT_ACKNOWLEDGED     = "analytics_alert_acknowledged"
ANALYTICS_ALERT_RESOLVED         = "analytics_alert_resolved"
BUSINESS_RECOMMENDATION_CREATED  = "business_recommendation_created"
BUSINESS_RECOMMENDATION_APPROVED = "business_recommendation_approved"
BUSINESS_RECOMMENDATION_REJECTED = "business_recommendation_rejected"
BUSINESS_RECOMMENDATION_EXPIRED  = "business_recommendation_expired"
SCENARIO_CREATED                 = "scenario_created"
SCENARIO_EVALUATED               = "scenario_evaluated"
ANALYTICAL_REPORT_GENERATED      = "analytical_report_generated"

__all__ += [
    "ANALYTICS_SNAPSHOT_CREATED",
    "FORECAST_RUN_STARTED",
    "FORECAST_RUN_COMPLETED",
    "FORECAST_RUN_FAILED",
    "FORECAST_MODEL_APPROVED",
    "FORECAST_MODEL_ACTIVATED",
    "FORECAST_MODEL_DEGRADED",
    "ANALYTICS_ALERT_CREATED",
    "ANALYTICS_ALERT_ACKNOWLEDGED",
    "ANALYTICS_ALERT_RESOLVED",
    "BUSINESS_RECOMMENDATION_CREATED",
    "BUSINESS_RECOMMENDATION_APPROVED",
    "BUSINESS_RECOMMENDATION_REJECTED",
    "BUSINESS_RECOMMENDATION_EXPIRED",
    "SCENARIO_CREATED",
    "SCENARIO_EVALUATED",
    "ANALYTICAL_REPORT_GENERATED",
]
