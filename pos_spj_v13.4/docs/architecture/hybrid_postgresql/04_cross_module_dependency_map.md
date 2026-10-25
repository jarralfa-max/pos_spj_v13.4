# 04 — Mapa de dependencias entre módulos

Fuente principal: `backend/bootstrap/wiring/event_wiring.py` (`wire_cross_context_events`, invocado en
`frontend/desktop/app.py` al arrancar), las concesiones de integración de
`backend/application/inventory/integration_grants.py` y los clientes de integración en
`backend/infrastructure/integrations/`.

## Cadena Compras → … → WhatsApp (estado medido)

| Tramo | Mecanismo real | Estado | Evidencia |
|---|---|---|---|
| Compras → Recepción → Inventario | `PURCHASE_STOCK_ENTRY_REGISTERED` → `CanonicalPurchaseStockEntryHandler` (hereda `PurchaseReceiptHandler`) → `PostInventoryMovementUseCase` con concesión `procurement` | **Vivo** | `event_wiring.py:222`; prueba `tests/integration/inventory/test_purchase_stock_entry_flip.py` (verde) |
| Reverso / devolución de compra → Inventario | `GOODS_RECEIPT_REVERSED`, `PURCHASE_RETURN_CONFIRMED` | Vivo | `event_wiring.py:235-245` |
| Inventario → Producción (Procesamiento cárnico) | Puertos de Procesamiento con concesión `meat_processing` (reserva, consumo, salida, lote, genealogía) | Vivo en la UI de Procesamiento | `backend/infrastructure/integrations/meat_processing_ports.py` |
| Producción → Costos → Precios | `costing_outbox` → `PRODUCTION_OUTPUT_COSTED` → costo promedio | Vivo con despacho | `dispatch_costing_outbox` |
| Transferencias ↔ Inventario | `transfers_inventory_gateway.py` con concesión `transfers` | Vivo; el ciclo aprobar/surtir/despachar/recibir quedó **habilitado en PERM-AUD 968e0bc** (antes se denegaba a todos) | `backend/application/transfers/cycle_service.py` |
| Ventas → Inventario | `SalesInventoryClient`: reserva con la política de sesión; salida y reingreso con la concesión `sales` | Vivo (POS) | `backend/infrastructure/integrations/sales_inventory_client.py` |
| Ventas → Caja | El cobro escribe en Caja dentro de la transacción de la venta (SALES-AUD V01) | Vivo | memoria `sales_audit_cebf67a` |
| Caja → Finanzas | `cash_outbox` → manejadores de Finanzas; despacho al arrancar y periódico | Vivo | `event_wiring.py:111`, CASH-AUD |
| Ventas → Finanzas | `sale_completed_handler`, `sale_returned_handler`, `sale_reversed_handler` | Vivo | `backend/application/event_handlers/finance/` |
| Ventas → Fidelidad | `sales_outbox` → acreditar, retirar o devolver canje | Vivo; **ronda FID 968e0bc sin cerrar** | `event_wiring.py:138-150` |
| Ventas → CRM | Cliente canónico `customers`; CRM consume eventos de cliente | Vivo | CRM-43/44 |
| Compras → Finanzas (CxP) | `procurement_payable_bridge`, pago inmediato | Vivo | `event_wiring.py:220-226` |
| RR. HH. → Finanzas | `hr_outbox` → nómina, préstamos | Vivo | HR-AUD |
| Pedidos → Inventario | `OrdersDeliveryInventoryClient` con concesión `orders_delivery` | Vivo | PERM-AUD 968e0bc |
| Pedidos → alertas internas | `OrdersDeliveryInternalNotifier` | **Corregido en PERM-AUD** (leía una tabla vacía) | — |
| BI | Consultas locales sobre SQLite (parte sobre `inventory_stock`) | Vivo, sólo local | `backend/application/analytics/` |
| WhatsApp → ERP | `whatsapp_service/erp/bridge.py` abre `ERP_DB_PATH` (el **mismo archivo SQLite**) | Vivo localmente; incompatible con multi-sucursal | `whatsapp_service/config/settings.py:52-56` |

## Dependencias rotas o heredadas detectadas

- **Paquetes borrados aún importados por pruebas:** `core`, `repositories`, `modulos`, `sync`, alrededor de
  20 pruebas. No se reponen: se adaptan o se retiran (regla del prompt §3.3).
- **Manejadores puente sin consumidor de producción:** `SaleItemsBridge`, `ProductionItemsBridge`
  (`backend/application/event_handlers/inventory/`). Candidatos a DEPRECAR.
- **Corte de Inventario (`INVENTORY_CANONICAL_CUTOVER`):** los manejadores canónicos de devolución de
  cliente y de producción sólo se suscriben con la bandera activa (`canonical_cutover.py`). Hay que
  verificar el estado de la bandera en cada instalación antes de replicar inventario.

## Qué implica para la replicación

Cada tramo vivo ya pasa por un **evento con `operation_id`** (idempotente localmente) y por un outbox de
contexto. Ese es el punto de captura natural de la replicación hacia el central: no hace falta capturar
cambios de tabla (CDC) ni duplicar la lógica de los manejadores.
