# ORD-19 — Fallas y reentregas

Fecha: 2026-08-31. Alcance: master prompt §40-41 (motivos, entrega fallida, retorno,
reentrega).

## Qué se construyó

- `FailureReason` (§40, 11 valores) — `DeliveryAttempt.create()` ahora VALIDA que
  `failure_reason` pertenezca a este catálogo cerrado (antes de esta fase aceptaba
  cualquier string no vacío).
- `RedeliveryRequest` (§41: motivo, ventana nueva, tarifa adicional, aprobador, estado) +
  `RedeliveryStatus` enum.
- `DeliveryJob.request_redelivery()`/`start_return()`/`complete_return()` — reutilizan
  transiciones que YA existían en `DeliveryLifecyclePolicy` desde ORD-15
  (FAILED→REDELIVERY_PENDING, FAILED→RETURNING→RETURNED_TO_BRANCH) pero que hasta ahora
  ningún método del agregado exponía.
- `RequestRedeliveryUseCase`, `ApproveRedeliveryUseCase`, `RejectRedeliveryUseCase`,
  `ReturnToBranchUseCase`.

## Decisión de diseño más importante de la fase

**Una reentrega SIEMPRE crea un `DeliveryJob` genuinamente nuevo — nunca reutiliza ni
redespacha el job fallido.** El job original queda permanentemente en
`REDELIVERY_PENDING` como registro histórico de qué falló;
`RedeliveryRequest.new_delivery_job_id` es bajo qué identidad corre el segundo intento.
Esto se decidió al leer con cuidado el propio campo `original_delivery_job_id` de §41 (el
prompt maestro ya asume que existen DOS jobs, uno "original" y uno nuevo) y evita el
riesgo de "reintento silencioso sobre el mismo intento fallido" que el prompt maestro
prohíbe explícitamente en su lista de qué eliminar ("fallbacks silenciosos").

## Decisiones menores

- **`ReturnToBranchUseCase` combina `start_return()` + `complete_return()` en una sola
  llamada** — no hay todavía necesidad de un paso intermedio "en camino de regreso"
  observable por separado; si aparece esa necesidad, dividir el caso de uso es un cambio
  aislado.
- **`ESCALATE`/`RETRY_SAME_DAY`/`CUSTOMER_PICKUP`/`CANCEL_ORDER` (las otras 4 decisiones
  de §40) NO se modelan como transiciones propias** — `RETRY_SAME_DAY` es simplemente
  reintentar el mismo `DeliveryJob` sin cambiar de estado (ya soportado: FAILED es un
  estado no-final que puede recibir un nuevo intento a través del mismo job si el
  `DispatchPolicy` lo permite — no construido explícitamente en esta fase por no ser una
  transición de estado distinta), `CANCEL_ORDER` reutiliza `CustomerOrder.cancel()`
  (ORD-2) y `job.cancel()` (ORD-15), `CUSTOMER_PICKUP`/`ESCALATE` son decisiones
  operativas sin modelo de dominio propio todavía.

## Tests

15 tests nuevos (9 dominio + 6 integración, esta última construyendo el pipeline REAL
completo hasta un intento fallido y luego solicitando/aprobando reentrega o retornando a
sucursal). Suite acumulada ORD-1..19: **282/282 pasando** (195 unitarios + 87 de
integración, verificados por separado).

## Pendiente

- Cobro contra entrega (ORD-20) — `cash_to_collect`/`payment_method_expected` ya existen
  en `DeliveryJob` desde ORD-15, sin lógica de cobro real todavía.
