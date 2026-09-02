# ORD-2 — Dominio de Pedidos (CustomerOrder)

Fecha: 2026-08-29
Alcance: master prompt §5, §11-17, §27, §42, §59, §74 (subset domain-detectable sin I/O).
Precede a ORD-3 (esquema) — mismo orden que SALES-3/LOY-2.

## Qué se construyó

Nuevo agregado `CustomerOrder`/`CustomerOrderLine`, pura capa de dominio (sin persistencia
todavía), distinto y separado de `DeliveryOrder`/`DeliveryItem` (`core/delivery/domain/
entities.py`, Estrato A de ORD-0) — master prompt §5: un Pedido es el compromiso operativo
del cliente, distinto de la Venta (documento fiscal) y de un futuro `DeliveryJob` (ejecución
de última milla, ORD-15+). El código legacy de `core/delivery/` sigue intacto y sigue
sirviendo `modulos/delivery.py` en producción; este agregado nuevo es la base para que
las fases siguientes (ORD-3+) construyan encima, no un reemplazo inmediato.

- `backend/domain/orders_delivery/enums.py` — `OrderChannel` (§6), `FulfillmentType` (§7),
  `OrderType` (§8), `OrderStatus`/`FulfillmentStatus`/`PaymentStatus`/
  `CustomerApprovalStatus` (§14-15, deliberadamente 4 enums separados, no uno fusionado),
  `OrderLineStatus` (§12).
- `backend/domain/orders_delivery/value_objects/{order_money,order_quantity,order_totals}.py`
  — mirrorean `backend/domain/sales/value_objects/{money,quantity,sale_totals}.py`
  exactamente. `OrderQuantity` sirve tanto para piezas como para peso (catch-weight); la
  política completa de ajuste/tolerancia es ORD-10.
- `backend/domain/orders_delivery/services/order_total_service.py` — `OrderTotalsService`,
  la única fuente de `OrderTotals` (subtotal/descuento/envío/impuesto/total). Es el
  reemplazo objetivo del shim `core/services/order_total_service.py` (ya autodeclarado como
  compatibility shim sobre `DeliveryTotalService`) — el shim NO se tocó todavía (ORD-29).
- `backend/domain/orders_delivery/policies/order_lifecycle_policy.py` —
  `OrderLifecyclePolicy` (tabla de transiciones enum-a-enum, mirror de
  `SaleLifecyclePolicy`), `OrderConfirmationPolicy`, `OrderCancellationPolicy`,
  `OrderReservationRequiredPolicy`.
- `backend/domain/orders_delivery/entities.py` — `CustomerOrder` (aggregate root) +
  `CustomerOrderLine` (owned entity), mirror exacto de `Sale`/`SaleLine`: dataclasses
  `slots=True`, `new_uuid()`/`validate_uuidv7()`, factories `create()`, mutaciones que
  delegan a políticas antes de tocar estado. `requested_subtotal`/`final_subtotal` son
  propiedades derivadas (nunca almacenadas) para que no puedan desincronizarse — mismo
  razonamiento que `SaleLine.line_total`.
- `backend/domain/orders_delivery/events.py` — `OrderEvents`/`order_event_payload()`,
  mirror exacto de `backend/domain/sales/events.py`. Es el catálogo canónico ÚNICO al que
  ORD-0 §2 identificó como necesario para resolver la triplicación de vocabularios de
  eventos — pero, igual que en Sales, es la vocabulario OBJETIVO, todavía NO conectado al
  EventBus real. `core/delivery/domain/events.py`'s `DeliveryEvents` sigue siendo lo que
  corre en producción hoy.
- Extensión de `backend/domain/orders_delivery/exceptions.py` con errores operativos:
  `OrderNotFoundError`, `OrderLineNotFoundError`, `InvalidOrderStateError`,
  `OrderConfirmationRequiredError`, `OrderEmptyError`, `OrderCancellationNotAllowedError`,
  `InvalidOrderQuantityError`, `InvalidOrderMoneyError`, `DuplicateOperationError`.

## Decisiones de diseño

- **Dos agregados, no uno fusionado**: a diferencia de `core/delivery/`'s `DeliveryOrder`
  (que mezcla pedido+entrega en una sola entidad), este dominio nuevo modela solo el
  Pedido. `DeliveryJob` (§31) se construye en ORD-15 como agregado separado que referencia
  `order_id`, nunca al revés.
- **Catch-weight a nivel de línea, no de política completa todavía**: `CustomerOrderLine`
  ya distingue `requested_quantity`/`requested_weight`/`prepared_*`/`final_*` y su
  `requested_subtotal`/`final_subtotal` ya cobran sobre peso cuando `catch_weight_enabled`,
  pero la política de tolerancia/aprobación del cliente (§26-27) es ORD-10/ORD-11.
- **`order_number`/folio no se autogenera aquí**: es un campo asignable externamente
  (str | None) — la generación de secuencia real (`PED-2026-000001`) requiere I/O
  (contador persistente), fuera del alcance de un dominio puro; se resuelve en la capa de
  aplicación/infraestructura de una fase posterior.

## Tests

24 tests nuevos, todos pasando:
- `tests/unit/test_orders_delivery_domain_entities.py` (19) — creación, líneas, totales
  derivados, confirmación, cancelación, ciclo de vida completo, catch-weight.
- `tests/unit/test_orders_delivery_domain_events.py` (5) — catálogo, payload, validación
  UUIDv7.

## Pendiente para fases futuras

- ORD-3: esquema `customer_orders`/`customer_order_lines` (UUIDv7, Decimal, constraints,
  outbox, bootstrap).
- ORD-15: agregado `DeliveryJob` separado.
- El bloqueador de identidad de cliente (`clientes.id` legacy vs `customers.id` UUIDv7,
  ORD-0 §4.1) sigue abierto; `CustomerOrder.customer_id` no asume todavía cuál de los dos
  espacios de identidad usará en persistencia — eso se decide en ORD-3.
