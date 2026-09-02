# ORD-23 — Notificaciones WhatsApp al cliente

Fecha: 2026-08-31. Alcance: master prompt §27/§30 (notificación al cliente cuando un
ajuste de peso o sustitución requiere su aprobación, y cuando un pedido está listo para
recoger). Tres use cases (ORD-10, ORD-12, ORD-14) documentaban explícitamente que este
paso quedaba pendiente "hasta que exista el gateway real de WhatsApp, ORD-23" — esta fase
cierra esa deuda.

## Qué se construyó

- `backend/infrastructure/integrations/orders_delivery_whatsapp_client.py` —
  `OrdersDeliveryWhatsAppClient`, un adaptador delgado sobre el cliente REST legacy YA
  FUNCIONAL `core.integrations.whatsapp_client.WhatsAppClient` (sin dependencias externas,
  resuelve URL/`X-Internal-Key` desde `configuraciones.wa_*` con fallback a `.env`, ya
  llama a los endpoints reales `/api/notify/pedido-listo` y `/api/notify/send` del
  microservicio). Clasificado REUSE, no reconstruido — mismo criterio que SALES-0 aplicó a
  `StockReservationService`. Nunca lanza excepciones: cualquier falla de red/microservicio
  se traduce en `False`.
- Notificación automática (best-effort, DESPUÉS de que la transacción del pedido ya se
  confirmó) cableada en tres puntos:
  - `EvaluateCatchWeightUseCase` (ORD-10) — cuando el peso queda fuera de tolerancia.
  - `ProposeSubstitutionUseCase` (ORD-12) — al proponer una sustitución.
  - `MarkReadyForPickupUseCase` (ORD-14) — al marcar el pedido listo (usa la plantilla
    dedicada `/api/notify/pedido-listo`, no el mensaje genérico).
  Las tres devuelven un campo `notification_sent: bool` en el resultado; una notificación
  fallida NUNCA revierte ni falla la operación de negocio que la disparó.
- `ResendCustomerApprovalNotificationUseCase` (nuevo,
  `backend/application/orders_delivery/use_cases/customer_notification_use_cases.py`) —
  acción manual de "reenviar", protegida por el permiso `CUSTOMER_APPROVAL_RESEND` (§63,
  existía desde ORD-1 sin ningún caso de uso que lo usara). Reconstruye el motivo
  (sustitución vs. ajuste de peso) a partir de las líneas en
  `PENDING_CUSTOMER_APPROVAL`.

## Decisiones

- **Inyección de dependencia, no un cliente global hardcodeado.** Las cuatro clases
  (`EvaluateCatchWeightUseCase`/`ProposeSubstitutionUseCase`/`MarkReadyForPickupUseCase`/
  `ResendCustomerApprovalNotificationUseCase`) aceptan `whatsapp_client` opcional en su
  constructor (default: instancia real) — permite pruebas rápidas y deterministas sin
  tocar la red real, y deja la puerta abierta a una implementación distinta en producción
  sin tocar el caso de uso.
- **Sin plantilla dedicada para "aprobación pendiente"** — a diferencia de
  `pedido-listo`/`anticipo`/`cotizacion`, el microservicio no tiene un endpoint específico
  para "tu pedido necesita tu aprobación", así que se usa el genérico `/api/notify/send`
  con un mensaje compuesto aquí. Agregar una plantilla dedicada en el microservicio
  quedaría del lado de `whatsapp_service`, fuera de este repositorio de fases ERP.
- **La conversación de dos vías (el cliente responde SÍ/NO) NO es parte de esta fase** —
  esto es ERP → cliente, un disparo saliente únicamente. Que el cliente responda y esa
  respuesta llegue de vuelta a `AcceptWeightAdjustmentUseCase`/`AcceptSubstitutionUseCase`
  es un flujo conversacional del microservicio (`whatsapp_service/flows/`), no de este
  bounded context.
- **`branch_name` se deja vacío** — `CustomerOrder` solo guarda `branch_id` (UUID), no un
  nombre de sucursal legible; resolverlo requeriría una consulta cruzada a `sucursales`
  que excede el alcance ajustado de esta fase. El endpoint del microservicio ya acepta
  `sucursal=""` sin problema.

## Efecto colateral encontrado y corregido: pruebas existentes ahora tocaban red real

Cablear la notificación automática dentro de casos de uso YA PROBADOS (ORD-10/12/14, y el
propio helper de pipeline de ORD-22) hizo que sus pruebas existentes, que no inyectan
ningún `whatsapp_client`, empezaran a intentar conexiones HTTP reales a
`http://localhost:8000` en cada corrida (silenciosamente atrapadas por el propio
try/except, así que seguían pasando, pero la suite completa de `orders_delivery` pasó de
~9s a ~39s). Se corrigió inyectando un stub `_NoOpWhatsAppClient` local en cada uno de esos
5 archivos de prueba — no es alcance ajeno, es una regresión de velocidad/higiene que esta
misma fase introdujo.

## Tests

19 tests nuevos (7 integración de los tres triggers automáticos + `Resend`, 6 unitarios de
`OrdersDeliveryWhatsAppClient` con un doble de prueba en vez de red real, más el
`_NoOpWhatsAppClient` inyectado en 5 archivos de prueba preexistentes). Suite completa de
`orders_delivery`: **348/348 pasando** en ~10s (de vuelta al orden de magnitud previo a
esta fase).

## Pendiente

- Plantilla dedicada de "aprobación pendiente" en el microservicio WhatsApp (mejora de
  UX, no bloqueante).
- Resolución de `branch_name` para el mensaje de "listo para recoger" (actualmente vacío).
- ORD-24 (dispatcher del outbox transaccional `orders_delivery_outbox`) — el siguiente
  paso explícito según la instrucción del usuario de continuar ORD-13 hasta ORD-24.
