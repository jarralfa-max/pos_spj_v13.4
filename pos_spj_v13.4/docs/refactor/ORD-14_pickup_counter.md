# ORD-14 — Pickup y counter

Fecha: 2026-08-31. Alcance: master prompt §30 (listo, validación de identidad, cobro,
entrega en mostrador).

## Qué se construyó

- `PickupPolicy` — valida modalidad (COUNTER/PICKUP), `fulfillment_status==READY`,
  código de verificación, y `payment_status==PAID` antes de la entrega.
- `CustomerOrder.pickup_verification_code` (campo nuevo) + `mark_ready_for_pickup()`/
  `complete_pickup()` (reutiliza `complete()` de ORD-2 en vez de duplicar la transición
  COMPLETED/DELIVERED).
- `MarkReadyForPickupUseCase` (genera un código numérico de 6 dígitos —
  `secrets.randbelow`, pensado para decirse/teclearse en mostrador, no un UUID),
  `CompletePickupUseCase`.

## Bug real encontrado y corregido antes de cerrar la fase

**`CustomerOrder.mark_reserved()` nunca avanzaba `OrderStatus` de `CONFIRMED` a
`IN_FULFILLMENT`** — desde ORD-8 (cuando `mark_reserved()` se creó) hasta ahora, ningún
código de este dominio disparaba esa transición. Como resultado, `complete()` (que exige
`IN_FULFILLMENT → COMPLETED`) nunca hubiera podido ejecutarse sobre un pedido real del
pipeline completo — solo lo demostró un test de dominio que reconstruía manualmente el
estado sin pasar por `mark_reserved()`. Corregido: `mark_reserved()` ahora llama
`move_to_fulfillment()` cuando el pedido está `CONFIRMED`. Verificado con la suite
completa antes/después — cero regresiones, y confirma que ORD-1..13 nunca llegaron a
ejercitar el camino "pedido completado" de punta a punta contra un pedido creado por los
casos de uso reales (solo contra entidades construidas a mano en tests unitarios).

## Decisiones

- **"Notificación" (§30, segundo paso) NO se construyó** — mismo motivo que "WhatsApp" en
  ORD-11: requiere el gateway real (ORD-23). `MarkReadyForPickupUseCase` ya produce el
  código de verificación que una notificación futura llevaría.
- **"Cobro si pendiente" no procesa pago aquí** — Pedidos no administra CxC/pagos (§47);
  esta fase solo GATEA sobre `payment_status`, un campo que el agregado ya posee desde
  ORD-2. Los tests fijan `payment_status='PAID'` directamente vía SQL, simulando lo que
  una integración real con Caja haría.
- **No se crea un `DeliveryJob` para pickup** — literal del prompt maestro §30: "No crear
  un DeliveryJob para pickup salvo necesidad de workflow común." `DeliveryJob` (ORD-15) es
  exclusivamente para modalidades de entrega a domicilio.

## Tests

13 tests nuevos (8 dominio + 5 integración, esta última con el pipeline REAL completo
hasta la entrega). Suite acumulada ORD-1..14: **201/201 pasando** (142 unitarios + 59 de
integración, verificados por separado).

## Pendiente

- Notificación real (ORD-23).
- Integración real de cobro (fuera del alcance de este bounded context, §47).
