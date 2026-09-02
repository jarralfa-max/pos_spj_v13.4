# ORD-15 — Delivery jobs

Fecha: 2026-08-31. Alcance: master prompt §31-32 (creación, asignación, estados).

## Qué se construyó

- **`DeliveryJob`** (`backend/domain/orders_delivery/delivery_job.py`) — el primer
  agregado genuinamente nuevo desde `CustomerOrder` (ORD-2). DELIBERADAMENTE SEPARADO del
  pedido (§5): referencia `order_id`, nunca al revés. Campos §31 completos (delivery_number,
  delivery_zone_id, prioridad, repartidor, ruta, ventana, ETA, timestamps de despacho/
  entrega/falla, tarifa, efectivo a cobrar, método de pago esperado).
- `DeliveryStatus` (§32, los 14 valores) + `DeliveryLifecyclePolicy` (tabla de
  transiciones completa) — ORD-15 solo cablea Creación/Asignación como casos de uso
  reales; el resto de los métodos del agregado (`dispatch/mark_in_transit/mark_arrived/
  start_delivery_attempt/mark_delivered/mark_failed/cancel/close`) ya existen para que
  ORD-16..19 los reutilicen sin reabrir esta fase ni inventar una segunda tabla de
  transiciones.
- `DeliveryEvents`/`delivery_event_payload()` — catálogo de eventos del lado Delivery
  (§59, segundo bloque), mismo patrón "vocabulario objetivo, no conectado al EventBus
  real todavía" que `OrderEvents` (ORD-2). `_OrdersDeliveryBaseUseCase._emit_delivery()`
  nuevo (mirror de `_emit()`).
- Esquema `delivery_jobs` (tabla nueva, `UNIQUE(operation_id)` para idempotencia,
  `UNIQUE(delivery_number)`), `DeliveryJobRepository`, wireado en `OrdersDeliveryUnitOfWork`.
- `CreateDeliveryJobUseCase` (idempotente por `operation_id`, mismo patrón que
  `CreateCustomerOrderUseCase`), `AssignDriverUseCase` — reutilizan `DELIVERY_CREATE`/
  `DRIVER_ASSIGN` de ORD-1.

## Bug real encontrado y corregido antes de cerrar la fase

**`DeliveryLifecyclePolicy.FINAL_STATUSES` incluía `DELIVERED`**, lo que bloqueaba la
transición legítima `DELIVERED → CLOSED` que la propia tabla `TRANSITIONS` define (el
chequeo de "estado final" se evalúa ANTES que la tabla de transiciones, así que un estado
mal clasificado como final bloquea sus propias transiciones válidas). Mismo tipo de bug
que `OrderLifecyclePolicy` ya evita deliberadamente (`OrderStatus.COMPLETED` NO está en
sus `FINAL_STATUSES` por la misma razón — completado todavía puede cerrarse/revertirse).
Corregido: `FINAL_STATUSES = {CANCELLED, CLOSED}` únicamente. Detectado por un test de
dominio que recorre el flujo feliz completo hasta `close()` — ningún test anterior había
ejercitado esa transición específica.

## Decisiones

- **`assign_driver()` no reutiliza la tabla de transiciones** — reasignar antes de
  despachar es válido desde PENDING_ASSIGNMENT o ASSIGNED, verificado directamente en vez
  de "forzar" la tabla con una entrada `(ASSIGNED, ASSIGNED)` que sería un self-loop
  extraño de justificar para las demás transiciones.
- **El caso de uso de creación NO vuelve a preguntarle a `CustomerOrder` si la modalidad
  necesita un DeliveryJob** — el prompt maestro §30 dice "No crear un DeliveryJob para
  pickup"; esa decisión la toma el LLAMADOR (una fase de orquestación futura), no este
  caso de uso, para evitar una dependencia circular entre los dos agregados (§5).
- **Sin validación cruzada de `driver_id` contra un repartidor real** — no existe todavía
  un directorio de repartidores (ORD-16 lo construye); `assign_driver()` solo valida que
  sea un UUIDv7 bien formado, igual que `DeliveryZoneRepository`/`OrderAddress` no validan
  referencias cruzadas a otros bounded contexts en fases anteriores.

## Tests

16 tests nuevos (10 dominio + 6 integración). Suite acumulada ORD-1..15: **217/217
pasando** (152 unitarios + 65 de integración, verificados por separado).

## Pendiente

- Perfil operativo de repartidor y disponibilidad (ORD-16).
- Rutas reales (ORD-17).
- Despacho/tracking/entrega/falla como casos de uso reales (ORD-18/19) — el agregado y la
  política ya soportan las transiciones, solo faltan los casos de uso que las invoquen.
