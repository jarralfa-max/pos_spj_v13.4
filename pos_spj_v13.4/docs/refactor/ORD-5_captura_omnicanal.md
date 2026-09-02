# ORD-5 — Captura omnicanal (Pedidos)

Fecha: 2026-08-29/30. Alcance: master prompt §17 (crear→confirmar→reservar), §18
(deduplicación). Primer consumidor real de `OrdersDeliveryAuthorizationPolicy.require()`
(ORD-1 dejó la política sin conectar deliberadamente).

## Qué se construyó

**Infraestructura de persistencia** (`backend/infrastructure/db/repositories/orders_delivery/`):
`base.py`, `customer_order_repository.py` (`CustomerOrderRepository.save()`/`get()`/
`find_by_operation_id()`/`find_by_channel_reference()`), `outbox_repository.py`,
`unit_of_work.py` (`OrdersDeliveryUnitOfWork`) — mirror exacto de la familia `sales/*`.

**Dominio**: `backend/domain/orders_delivery/policies/order_deduplication_policy.py` —
`OrderDeduplicationPolicy.resolve_existing()`, política pura (sin I/O): dado lo que el
repositorio ya encontró por `operation_id`/`(channel, external_order_reference)`, decide
si la petición es un reintento (retorna el pedido existente) o es genuinamente nueva.

**Aplicación**: `backend/application/orders_delivery/{result,dto}.py` (mirror de
`sales/result.py`/`dto.py`), `use_cases/{_base,order_capture_use_cases}.py` —
`CreateCustomerOrderUseCase`, `ConfirmCustomerOrderUseCase`.

## Decisiones

- **Un solo `CreateCustomerOrderUseCase` para todos los canales** (master prompt §1: "No
  crear sistemas paralelos para pedidos POS/WhatsApp/..."). POS, WhatsApp, Counter,
  Backoffice y API llamarán este MISMO caso de uso con distinto `channel`/
  `external_order_reference` — no se construyó ningún "flujo de captura" específico por
  canal en esta fase; los adaptadores de canal (webhook WhatsApp, pantalla POS) son trabajo
  de integración de una fase posterior, no de este dominio.
- **Idempotencia por retorno, no por error**: a diferencia de un `DuplicateOperationError`
  genérico, un reintento con el mismo `operation_id` o el mismo `(channel,
  external_order_reference)` retorna `OrderResult.ok()` con el pedido YA existente — un
  webhook de WhatsApp reintentando no debe fallar, debe recibir la misma respuesta que la
  primera vez.
- **Confirmación separada de creación**: `ConfirmCustomerOrderUseCase` es su propio caso de
  uso (no un parámetro `auto_confirm` en create) — deja espacio para que ORD-6+
  (programados) y flujos de aprobación intercalen pasos entre captura y confirmación sin
  reabrir esta fase.

## Tests

11 tests de integración (`tests/integration/test_orders_delivery_capture_use_cases.py`)
contra SQLite real con el esquema de ORD-3: creación con líneas, denegación por permiso,
idempotencia por `operation_id`, idempotencia por `(channel, external_order_reference)`
(caso WhatsApp explícito), no-colisión entre canales distintos con la misma referencia
cruda, rechazo de línea sin cantidad/peso, persistencia/recarga de línea catch-weight,
confirmación (incluye doble-confirmación inválida, pedido inexistente, evento en outbox).

Suite completa ORD-1..5: 76/76 tests pasando.

## Pendiente

- ORD-6 (programados), ORD-7 (direcciones/zonas), ORD-8 (inventario) construyen sobre este
  mismo `CreateCustomerOrderUseCase`/`CustomerOrder`, no lo reemplazan.
- Adaptadores de canal reales (webhook WhatsApp → este UseCase, pantalla POS → este
  UseCase) no se construyeron — son trabajo de integración cross-context, fuera del
  alcance de "dominio + aplicación" de esta fase.
