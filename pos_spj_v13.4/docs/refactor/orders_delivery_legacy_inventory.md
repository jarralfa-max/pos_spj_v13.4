# Pedidos / Delivery / Última Milla — ORD-0 Auditoría de Legacy

Fecha: 2026-08-28
Fase: **ORD-0 (Auditoría)** del bounded context "Orders and Delivery" (prompt maestro
Pedidos/Delivery). Precede a `ORD-1..ORD-30`. No se tocó código en esta fase, solo
inventario y clasificación.

## 0. Hallazgo raíz

A diferencia de lo que asume el prompt maestro, este módulo **no es legacy sin tocar**.
Existen tres estratos superpuestos:

- **Estrato A** — `core/delivery/` (domain + application + infrastructure + projections):
  una implementación DDD ya madura, con máquina de estados, políticas, casos de uso,
  outbox transaccional, proyecciones a ventas/inventario y ~30 archivos de tests
  (unit + integración + arquitectura). Vive bajo `core/` en vez de `backend/`, pero
  funcionalmente ya cumple buena parte de lo que el prompt maestro pide en
  §9.3 (dominio) y §9.4 (aplicación).
- **Estrato B** — Scaffolding ya insertado en `backend/application/{commands,use_cases,queries}/`
  con el patrón `DelegatingUseCase` (shells `not_implemented`), salvo
  `settle_delivery_driver_use_case.py` y `driver_settlement_query_service.py` que sí
  tienen lógica real. Nadie conectó los shells todavía.
- **Estrato C** — Puntos de integración de solo lectura ya construidos por CRM/Customers
  (`customer_delivery_summary_query.py`, `customer_orders_summary_query.py`) que
  documentan textualmente el nombre "Orders/Delivery" como bounded context destino y
  dejan constancia de que Delivery hoy escribe contra `clientes.id` legacy, no
  `customers.id` UUIDv7 — un bloqueador cruzado real.

**Consecuencia para el plan:** ORD-2..ORD-4 (dominio, esquema, sidebar) deben tratarse
como **relocalización + limpieza** del Estrato A hacia `backend/domain/orders_delivery/`
y `backend/application/orders_delivery/`, no como reescritura desde cero. Reescritura
completa sí aplica a: PWA de repartidor, catálogo de eventos, permisos, y unificación de
esquema (ver clasificación abajo).

`docs/refactor/modules/delivery.md` (Fase A, 2026-0x) ya cerró una limpieza puntual de
identidad/defaults en `modulos/delivery.py` (branch_id `int`/default `1` → `str`/`""`).
Ese trabajo queda vigente y no se repite aquí.

## 1. Inventario por archivo (rutas relativas a `pos_spj_v13.4/pos_spj_v13.4/` salvo WhatsApp)

### Dominio y aplicación (Estrato A) — candidato REUSE, mover a `backend/`

| Archivo | Contenido | Clasificación |
|---|---|---|
| `core/delivery/domain/entities.py` | `DeliveryOrder`, `DeliveryItem` | REUSE → mover a `backend/domain/orders_delivery/entities/` |
| `core/delivery/domain/events.py` | `DeliveryEvents` StrEnum (canónico más reciente) | REUSE, base del catálogo único (§59 del prompt) |
| `core/delivery/domain/policies.py` | `WeightAdjustmentPolicy` | REUSE → `policies/catch_weight_adjustment_policy.py` |
| `core/delivery/domain/print_policy.py` | `DeliveryPrintPolicy` | REUSE |
| `core/delivery/domain/credit_policy.py` | `requires_credit_check()` | REUSE → `policies/cash_on_delivery_policy.py` |
| `core/delivery/domain/state_machine.py` | `DeliveryStateMachine` | REUSE → separar en `OrderStateMachine`/`DeliveryStateMachine` (prompt §16 pide dos, hoy hay una fusionada) |
| `core/delivery/domain/states.py` | `DeliveryWorkflowType`, `DeliveryType`, `AdjustmentStatus` | REUSE, mapear a enums canónicos §14/§15 |
| `core/delivery/domain/value_objects.py` | `Quantity`, `DeliveryStatus`, `FulfillmentType`, `PaymentStatus`, `UnitCode` | REUSE |
| `core/delivery/domain/workflow_policy.py` | `DeliveryWorkflowPolicy` | REUSE |
| `core/delivery/application/create_delivery_order.py` | `CreateDeliveryOrderUseCase` | REUSE, conectar a shell de `backend/application/use_cases/create_delivery_order_use_case.py` |
| `core/delivery/application/assign_delivery_driver.py` | `AssignDeliveryDriverUseCase` | REUSE |
| `core/delivery/application/change_delivery_status.py` | `ChangeDeliveryStatusUseCase` (313 líneas, orquestador central) | REUSE, es el corazón de la máquina de estados |
| `core/delivery/application/cancel_delivery_order.py` | `CancelDeliveryOrderUseCase` | REUSE |
| `core/delivery/application/activate_scheduled_order.py` | `ActivateScheduledOrderUseCase` | REUSE → base de ORD-6 (programados) |
| `core/delivery/application/adjust_delivery_weight.py` | `AdjustDeliveryWeightUseCase` (226 líneas) | REUSE → base de ORD-10 (peso variable) |
| `core/delivery/application/approve_delivery_adjustment.py` | aprobación cliente vía WA | REUSE → base de ORD-11 |
| `core/delivery/application/sync_whatsapp_orders.py` | `SyncWhatsAppOrdersUseCase` | REUSE, revisar si sigue vs. dedupe canónico §18 |
| `core/delivery/application/query_service.py` | `DeliveryQueryService` (719 líneas, ruta de lectura única) | REUSE → mover, dividir por página si crece demasiado |
| `core/delivery/application/ports.py` | `EventPublisher`, `StatusNotifier`, `GeocodingPort` | REUSE → `repository_ports.py`/puertos de dominio |
| `core/delivery/application/dto.py` | `DeliveryOrderViewDTO`, `DeliveryItemViewDTO` | REUSE |
| `core/delivery/application/legacy_event_bridge.py` | bridge `DeliveryEvents` → strings legacy | DELETE una vez el catálogo único (§59) sea el único consumido — no antes |
| `core/delivery/application/process_delivery_outbox.py` | `ProcessDeliveryOutboxUseCase` | REUSE → base de ORD-24 |
| `core/delivery/application/print_coordinator.py` | `DeliveryPrintCoordinator` | REUSE |
| `core/delivery/application/kanban_config.py` | columnas Kanban | REUSE, mover a frontend view-model |
| `core/delivery/application/action_dispatcher.py` | `DeliveryActionDispatcher` | REUSE |
| `core/delivery/application/action_policy.py` | `DeliveryActionPolicy` | REUSE |
| `core/delivery/application/quantity_formatter.py` | `QuantityFormatter` | REUSE |
| `core/delivery/application/delivery_total_service.py` | `DeliveryTotalService` | REUSE → `order_total_service.py` de dominio |
| `core/delivery/infrastructure/delivery_schema_migrator.py` | **dueño real del esquema hoy** | MOVE + auditar contra §75.15 (ver §3) |
| `core/delivery/infrastructure/delivery_outbox_repository.py` | `DeliveryOutboxRepository` | REUSE |
| `core/delivery/infrastructure/whatsapp_delivery_notifier.py` | `WhatsAppDeliveryNotifier` | REUSE → `WhatsAppOrderNotifier` |
| `core/delivery/projections/sale_delivery_projection.py` | `SaleDeliveryProjectionService` (push a `ventas`) | REWRITE como evento consumido por Sales, no push directo (viola §49 del prompt) |
| `core/delivery/projections/delivery_inventory_projection.py` | `DeliveryInventoryProjectionService` | REUSE, ya respeta el puerto de Inventario |

### Servicios/repositorios legacy sueltos

| Archivo | Clasificación |
|---|---|
| `core/services/delivery_service.py` | WRAP_TEMPORARILY — ya es fachada delgada sobre Estrato A; eliminar cuando UI nueva llame UseCases directo |
| `core/services/driver_service.py` | MOVE, con validaciones reales a preservar |
| `core/services/order_total_service.py` | DELETE (shim autodeclarado) |
| `core/services/order_badge_service.py` | REUSE → alimentar badges del sidebar §68 |
| `core/services/reservation_service.py` | REUSE, es la base real de ORD-8 (reservas) |
| `core/services/stock_reservation_service.py` | NO TOCAR (pertenece a ventas suspendidas, contexto distinto) — solo documentar para no confundir nombres |
| `core/services/pedidos_whatsapp_service.py` | REWRITE hacia el núcleo único de pedidos (elimina tabla paralela `pedidos_whatsapp`, ver §3) |
| `core/services/delivery_whatsapp_service.py` | WRAP_TEMPORARILY, consolidar en `WhatsAppOrderNotifier` |
| `repositories/delivery_repository.py` | MOVE, partir en `customer_order_repository.py` + `delivery_job_repository.py` |
| `repositories/driver_repository.py` | MOVE (su `ensure_schema()` ya es no-op "born-clean", buena señal) |
| `core/use_cases/pedido_wa.py` | REUSE como base de deduplicación (§18), ya consolidó 3 flujos previos |
| `services/bot_pedidos.py` (893 líneas) | BLOCKED — decidir si sigue vivo en producción o si `whatsapp_service/flows/pedido_flow.py` ya lo reemplazó antes de clasificar DELETE |
| `delivery/ticket_delivery.py`, `delivery/mapas_qr.py`, `delivery/asignacion_repartidor.py` | MOVE a `infrastructure/printing/` e `infrastructure/geocoding/` respectivamente |

### UI legacy

| Archivo | Clasificación |
|---|---|
| `modulos/delivery.py` (2991 líneas) | REWRITE de UI (mover a `frontend/desktop/modules/orders_delivery/`), pero su lógica de negocio YA fue removida (0 SQL, 0 defaults arbitrarios de sucursal — ver Fase A previa). Es un port de presentación, no una reescritura de reglas. |
| `modulos/whatsapp/*` | NO ES DELIVERY — administración de conexión/credenciales WhatsApp, fuera de alcance de este bounded context |

### PWA repartidor

| Archivo | Clasificación |
|---|---|
| `integrations/delivery_pwa/pwa_server.py` | REWRITE completo — servidor HTTP artesanal, HTML inline en strings Python, tokens en memoria sin persistencia, polling. No cumple §9.2/§66 (offline-first, outbox, operation_id). Usar `frontend/web/logistics/` (PWA hermana de Procurement) como plantilla estructural de manifest/service-worker/offline-sync — no como código a copiar. |

### Esquema (ver detalle completo en §3)

Tablas existentes: `delivery_orders`, `delivery_items`, `delivery_order_history`, `drivers`,
`driver_locations`, `delivery_driver_cuts`, `delivery_outbox_events`, `delivery_print_log`,
`pedidos_whatsapp`, `pedidos_whatsapp_items`, `bot_sessions`, `whatsapp_queue`, `links_pago`,
`inventory_reservations` (compartida con reservas generales).

No existen (a construir en ORD-3/ORD-7/ORD-17): `delivery_zones`, `delivery_routes`,
`delivery_route_stops`, tabla de repartidores en inglés separada de personal (hoy `drivers`
ya está en inglés, correcto).

## 2. Vocabulario de eventos triplicado (bloqueador de ORD-2/ORD-59)

Coexisten simultáneamente tres catálogos para los mismos conceptos:

1. `core/events/event_bus.py` — constantes sueltas (`PEDIDO_NUEVO`, `DELIVERY_ORDER_CREATED`, ...).
2. `core/delivery/domain/events.py` — `DeliveryEvents` StrEnum (el más limpio de los tres).
3. `backend/shared/events/event_names.py` — subconjunto incipiente ya en inglés puro.

Puenteados manualmente por `core/delivery/application/legacy_event_bridge.py`. **Decisión
requerida antes de ORD-2**: promover `DeliveryEvents` (ajustado a los nombres canónicos del
prompt §59, ej. `ORDER_CREATED` → `CustomerOrder` vs `DeliveryJob`) a única fuente y
desactivar los otros dos, no fusionar los tres.

## 3. Triplicación de dueño de esquema (bloqueador de ORD-3)

- `migrations/m000_base_schema.py` — TEXT PK (UUIDv7), correcto.
- `migrations/093_create_delivery_core.sql` + `094_add_delivery_outbox.sql` +
  `095_add_delivery_history_audit.sql` — declaran `INTEGER PRIMARY KEY AUTOINCREMENT`,
  claramente anteriores a la Regla Cero UUIDv7. **No son la fuente que corre hoy.**
- `core/delivery/infrastructure/delivery_schema_migrator.py` (`DeliverySchemaMigrator`) —
  dueño real en runtime, TEXT PK, `ALTER TABLE ADD COLUMN` idempotente acumulado.

Antes de ORD-3 hay que: (a) confirmar que ninguna instalación viva depende todavía de
093/094/095 corriendo desde cero, (b) si no, marcarlas `DROP` documentado, (c) fusionar
`DeliverySchemaMigrator` dentro de `migrations/standalone/` numerado siguiendo convención
del proyecto, retirando el migrador ad-hoc como mecanismo permanente.

`delivery_order_history.historial_cambios` (columna JSON en `delivery_orders`) ya está
marcada deprecated desde la migración 095 a favor de la tabla `delivery_order_history` —
alineado con §75.8 del prompt maestro; solo falta el DROP final de la columna y sus
consumidores.

## 4. Bloqueadores cruzados (requieren decisión de producto, no solo código)

1. **Identidad de cliente**: `delivery_orders.cliente_id` guarda `clientes.id` legacy, no
   `customers.id` UUIDv7. CRM ya documentó esto en `customer_delivery_summary_query.py` /
   `customer_orders_summary_query.py` como pendiente "CRM-21/22". Orders/Delivery no puede
   declararse dueño limpio de la relación con cliente hasta resolver este puente.
2. **`services/bot_pedidos.py` vs `whatsapp_service/flows/pedido_flow.py`**: ambos son flujos
   conversacionales completos de toma de pedido por WhatsApp. Hay que verificar en runtime
   cuál está realmente sirviendo tráfico antes de eliminar cualquiera (prompt §75.17 exige
   cero-consumidores confirmado, no solo lectura de código).
3. **`SaleDeliveryProjectionService`**: hoy Delivery escribe directamente en `ventas`
   (push unidireccional). El prompt maestro (§49) prohíbe que el repository de pedidos
   actualice `ventas` directamente — requiere decidir si Sales expone un UseCase de
   actualización o si se reemplaza por evento + proyección propia de Sales.
4. **Permisos**: `core/security/permission_catalog.py` no tiene NINGÚN código
   `DELIVERY_*`/`ORDERS_*`/`PEDIDOS_*`/`DRIVER_*` hoy. El control de acceso actual de
   `modulos/delivery.py` es, en el mejor caso, visibilidad de módulo, no permisos
   granulares. ORD-1 (seguridad) debe partir de cero aquí, no de una migración.

## 5. Cobertura de tests existente (activo a preservar como oráculo de regresión)

~30 archivos de test unitario/integración/arquitectura ya cubren Estrato A (máquina de
estados, políticas, outbox, proyecciones, impresión, `DeliveryQueryService`, etc.), más
`tests/architecture/test_delivery_guardrails.py` (ratchet en cero) y
`test_delivery_architecture.py`. Estrategia recomendada: **mover los tests junto con el
código que auditan** (mismo commit) en vez de reescribirlos desde cero, y solo agregar
tests nuevos para lo que hoy no existe (zonas, rutas, permisos, PWA nueva, catálogo de
eventos único).

Sin cobertura hoy: flujos de `whatsapp_service` propios, `integrations/delivery_pwa/`,
`services/bot_pedidos.py`.

## 6. Recomendación de secuencia (ajuste sobre ORD-1..ORD-30 del prompt maestro)

Dado que el dominio/aplicación ya existen (Estrato A), la secuencia de mayor apalancamiento es:

1. **ORD-1 (seguridad)** — permisos desde cero (§4.4), es el gap más real y barato de cerrar primero.
2. **ORD-2/ORD-3** — mover Estrato A a `backend/domain|application/orders_delivery/` +
   consolidar esquema (resolver §3 antes de escribir una sola migración nueva).
3. Resolver bloqueadores §4.1 y §4.3 (identidad cliente, proyección a ventas) como
   prerequisito de ORD-8 (inventario) y ORD-22 (ventas/finanzas), no en paralelo.
4. PWA (ORD-25) y zonas/rutas (ORD-7/ORD-17) son la construcción genuinamente nueva —
   ahí sí aplica "greenfield" en el sentido que asume el prompt maestro.

## 7. Estado

Este documento cierra **ORD-0**. Ninguna clasificación aquí es definitiva sin
confirmar cero-consumidores (§75.17 del prompt) antes de cualquier DELETE. Siguiente
paso: ORD-1 (permisos) tras validación con el usuario del orden de prioridad de §6.
