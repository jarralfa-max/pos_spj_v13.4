# ORD-18 — Despacho y entrega

Fecha: 2026-08-31. Alcance: master prompt §36-40 (despacho, seguimiento, llegada,
evidencia, entrega).

## Qué se construyó

- `DispatchPolicy` — valida pedido listo (`FulfillmentStatus.READY`), sin aprobación de
  cliente pendiente, repartidor asignado. Empaque/ticket quedan fuera del dominio
  (infraestructura de impresión, ORD-28).
- `DeliveryEvidence` (VO) + `DeliveryAttempt` (entidad, embebida en `DeliveryJob` igual
  que `CustomerOrderLine` en `CustomerOrder`) — una entrega exitosa exige evidencia
  (receptor/firma/foto/PIN/geo, al menos uno), una fallida exige motivo.
  `DeliveryJob.record_attempt()` resuelve el estado del job desde el resultado.
- `CustomerOrder.mark_dispatched()`/`complete_delivery()` — el pedido tiene su propia
  vista de `FulfillmentStatus` (DISPATCHED/DELIVERED) independiente del estado interno del
  `DeliveryJob`; ninguno de los dos agregados referencia al otro (§5), la capa de
  aplicación orquesta ambos en una sola transacción.
- Casos de uso: `DispatchDeliveryJobUseCase` (actualiza AMBOS agregados),
  `MarkInTransitUseCase`, `ConfirmArrivalUseCase`, `RecordDeliveryAttemptUseCase` (en
  éxito llama `order.complete_delivery()`; en falla NO completa el pedido — eso es ORD-19).

## Decisiones

- **Cobro no se valida en `complete_delivery()`** — a diferencia de `complete_pickup()`
  (que sí exige `PAID`), la entrega a domicilio puede cobrarse contra entrega (§20); esa
  validación es explícitamente ORD-20 ("Pagos contra entrega"), no esta fase.
- **"Seguimiento" (§37) no tiene tabla de eventos propia** — los estados IN_TRANSIT/
  ARRIVED ya construidos en ORD-15, más el catálogo `DeliveryEvents` (OUT_FOR_DELIVERY/
  ARRIVED), ya cubren la granularidad que un log de tracking necesitaría; no se duplicó
  con una tabla adicional.
- **Un intento fallido NO completa ni cancela el pedido** — solo dispara
  `DeliveryStatus.FAILED`. Reentrega/retorno a sucursal es ORD-19.

## Tests

19 tests nuevos (13 dominio + 6 integración). La suite de integración construye el
pipeline REAL completo por primera vez: capturar→confirmar→reservar→preparar→crear job→
registrar/proponer/aceptar repartidor→despachar→tránsito→llegada→entregar, contra ambos
esquemas (orders_delivery + inventory) en la misma conexión. Suite acumulada ORD-1..18:
**267/267 pasando** (186 unitarios + 81 de integración, verificados por separado).

## Pendiente

- Fallas y reentregas como flujo propio (ORD-19) — hoy un intento fallido solo dispara
  `DeliveryStatus.FAILED`, sin lógica de reintento/retorno.
- Cobro contra entrega (ORD-20).
