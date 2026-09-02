# ORD-24 — Dispatcher del outbox transaccional

Fecha: 2026-08-31. Alcance: master prompt §57-58. Cierra el rango que el usuario pidió
explícitamente ("continua con ORD-13 hasta ORD-24"). Cada fase anterior (ORD-2, ORD-3,
ORD-15, y el propio `outbox_repository.py` desde ORD-3) dejó el mismo comentario: "no
dispatcher exists yet — ORD-24 builds it".

## Qué se construyó

- `backend/application/orders_delivery/integrations/orders_delivery_outbox_dispatcher.py`
  — `dispatch_orders_delivery_outbox(connection, bus, *, limit=100, max_attempts=5)`.
  Mirrors `backend/application/procurement/integrations/procurement_outbox_dispatcher.py`
  exactamente: lee filas `PENDING` de `orders_delivery_outbox`, valida que el payload JSON
  coincida con la fila (event_id/event_name/operation_id), publica en el `EventBus` real
  (`core.events.event_bus.EventBus.publish(event_type, payload, async_=False)`), marca
  `DONE` en éxito o aplica backoff exponencial (`DEAD_LETTER` al agotar `max_attempts`) en
  fallo.
- Los eventos publicados (`OrderEvents`/`DeliveryEvents`, construidos desde ORD-2/15) NO
  tienen NINGÚN suscriptor real todavía — cada fase anterior lo documentó explícitamente.
  `EventBus.publish(strict=False)` solo loguea cuando nadie escucha, no lanza, así que
  cablear este dispatcher AHORA es seguro aunque nada lo consuma todavía; una fase futura
  agrega handlers sin tocar este módulo.

## Bug real encontrado y corregido (el 7º de este pipeline, y el primero puramente de
infraestructura de persistencia, no de política de dominio)

`OrdersDeliveryOutboxRepository.mark_failed()` (construido en ORD-3) ponía la fila en
`status='FAILED'` de forma incondicional, pero `list_pending()` solo seleccionaba
`status='PENDING'` — una fila marcada como fallida quedaba **muerta para siempre**, sin
ningún mecanismo que la reintentara, a pesar de que las columnas `retries`/`next_retry_at`
claramente anticipaban un ciclo de reintento. El bug estaba dormido desde ORD-3 porque
nada llamaba `mark_failed()` hasta que este dispatcher existió. Corregido mirando
`ProcurementOutboxRepository.mark_failed()` (mismo patrón ya resuelto en otro bounded
context): la fila permanece `PENDING` con un `next_retry_at` futuro que `list_pending()`
ahora sí respeta (`WHERE status='PENDING' AND (next_retry_at IS NULL OR
next_retry_at<=?)`), y solo pasa a `DEAD_LETTER` (nuevo valor de `status`, sin migración
de esquema — la columna nunca tuvo `CHECK`) al agotar `max_attempts`.

## Decisiones

- **Módulo función-suelta, no una clase** — mismo patrón que
  `dispatch_procurement_outbox`; no hay estado que justifique una clase, y el módulo ya
  existente en este codebase para exactamente este problema (outbox de un solo destino,
  sin sincronización multi-nodo) usa esa forma. `InventoryOutboxDispatcher` (con estado de
  secuencia/nodo) es un problema DISTINTO — sincronización offline-first multi-nodo — y no
  aplica aquí; `orders_delivery_outbox` no tiene esa infraestructura ni la necesita.
- **El dispatcher es la frontera de transacción de su propia contabilidad** — los
  repositorios nunca hacen commit (`base.py` es explícito sobre esto); esta función llama
  `connection.commit()` al final si algo cambió, deliberadamente separado de cualquier
  `OrdersDeliveryUnitOfWork` que haya encolado las filas originalmente.
- **No se agregó un cron/scheduler real** — esta fase entrega la función pura de
  despacho; invocarla periódicamente (hilo en segundo plano, tarea programada, endpoint
  manual) es una decisión de composición/arranque de la aplicación, fuera del alcance de
  "construir el dispatcher" en sí.

## Tests

8 tests nuevos: despacho exitoso (incluye un smoke test contra el `EventBus` real,
singleton de todo el proceso, con suscripción/desuscripción propia para no filtrar estado
a otras pruebas), reintento con backoff, promoción a `DEAD_LETTER` al agotar intentos, y
payload corrupto tratado como reintentable en vez de crashear. Suite completa de
`orders_delivery`: **356/356 pasando**.

## Pendiente

- Wiring de un scheduler/cron real que invoque `dispatch_orders_delivery_outbox`
  periódicamente (fuera de alcance, ver arriba).
- Handlers reales para `OrderEvents`/`DeliveryEvents` — el vocabulario ya es publicable,
  pero nada lo consume todavía.
- Esto cierra el rango "ORD-13 hasta ORD-24" pedido explícitamente por el usuario. La
  autorización más amplia "ORD-2 hasta ORD-30" sigue abierta para continuar si se solicita.
