# Clientes y CRM — mapa de integraciones (CRM-43, 2026-10-09)

Regla: Clientes identifica, CRM relaciona, Ventas vende, Fidelidad recompensa, Finanzas
contabiliza, WhatsApp conversa, Delivery entrega, BI analiza. CRM nunca escribe en tablas
de otro contexto.

| Contexto | Qué ve/hace CRM | Cómo | Estado CRM-43 |
|----------|-----------------|------|---------------|
| Ventas / POS | Búsqueda y alta rápida de cliente en el POS | `SalesCustomerClient` → `CustomerLookupQueryService` / `CreateCustomerUseCase` | Cajero ya puede buscar (`CLIENTES.buscar`, migr. 314) |
| Ventas / POS | Elegibilidad de venta a crédito | `SalesCreditClient` → `CheckCreditSaleEligibilityUseCase` | Permiso corregido (`elegibilidad_comercial.verificar`), mensajes de §39, tipo y estatus del maestro |
| Ventas → Clientes | Número de compras, última compra, etapa del cliente | bus canónico: `SALE_COMPLETED` / `SALE_REVERSED` → `wire_customers_sales` | Reconectado (estaba en `core/events`, borrado) + migr. 316 |
| Ventas | Compras, pagos, devoluciones, productos frecuentes | `CustomerHistoryQueryService.get_*` (lectura de `sales`, `sale_payments`, `sale_returns`, `sale_lines`) | Nuevo |
| Pedidos y Delivery | Pedidos del cliente, resumen de entregas | `get_order_history` (`customer_orders`), `CustomerDeliverySummaryQuery` | Nuevo / existente |
| Cotizaciones | Alta desde la oportunidad, historial del cliente | contexto propio `quotes` (§50); `get_quote_history` lee `quotes` | Construido (migr. 318/319) |
| Cotizaciones → Pedidos | Cotización aceptada a pedido | `ConvertQuoteToOrderUseCase` → `CreateCustomerOrderUseCase(order_type=QUOTE_CONVERTED, quote_id)` | Construido (migr. 320) |
| Cotizaciones → Precios | Precio de lista y mínimo | `PricingReadFacade.sale_price` (canal `SALES_REP`, cliente, cantidad) | Construido |
| Finanzas / CxC | Exposición, vencido, próximo vencimiento | `CustomerAccountsReceivableSummaryQuery` (lee `receivables` y `cuentas_por_cobrar`) | Existente, ahora visible en Crédito → CxC |
| Finanzas | Navegación a la CxC del cliente | `NavigationIntent("finance.receivables")` | Existente |
| Fidelidad | Programa, puntos, nivel | `LoyaltyCustomerSummaryQuery` (sólo lectura) | Existente; las acciones viven en Fidelidad |
| WhatsApp | Consentimiento, conversaciones, avisos (sin contenido) | `CustomerWhatsAppSummaryQuery`, `CustomerChannelHistoryRepository` | Nuevo historial (metadatos) |
| Notificaciones | Recordatorios y avisos de automatizaciones | `DispatchDueCRMRemindersUseCase` y `SEND_NOTIFICATION` → `notification_inbox` → campana (`NotificationInboxFeed`) | Entrega real (migr. 317), ciclo de fondo cada 5 min |
| BI | Indicadores operativos del tablero | `CRMInsightsQueryService`, `CRMBIExportQueryService` | Nuevo |
| Seguridad | Permisos, alcance, segregación | `CustomerSessionPermissionChecker`, resolvedores de alcance | Matriz sembrada (314), ejes BRANCH/COMPANY |
