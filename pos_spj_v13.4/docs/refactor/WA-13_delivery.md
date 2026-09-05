# WA-13 — Delivery (canal WhatsApp)

Ejecutado: 2026-09-01/02. §35, §19 del prompt maestro. Primera fase del
batch WA-13..WA-18 pedido en esta sesión.

## Qué se construyó

- `domain/whatsapp/entities/delivery_request.py::DeliveryRequest` — el
  rastro conversacional de "el cliente pidió programar entrega a domicilio
  para el pedido X, con esta dirección". Mismo criterio que `OrderDraft`
  (WA-10)/`QuoteDraft` (WA-11): no es el estado operativo real de la
  entrega (eso lo posee Orders/Delivery,
  `orders_delivery_enterprise_transformation`, ya completo con 418 tests) —
  es lo que el canal registró y si el ERP aceptó la solicitud. Estado
  propio: `REQUESTED → SCHEDULED | FAILED`.
- Migración **246** (`whatsapp_delivery_requests`, 1 tabla nueva —
  `create_whatsapp_schema()` sigue siendo el único módulo de DDL, mismo
  patrón desde WA-3).
- `infrastructure/persistence/sqlite_delivery_request_repository.py` —
  `get_by_order_external_id` desempata con `id DESC` (UUIDv7, ordenado por
  tiempo) cuando dos intentos comparten `created_at`, mismo criterio que
  `customer_consent_repository.py::get_latest` (CRM-9).
- `application/delivery_request_service.py::DeliveryRequestService.request_delivery()`
  — orquesta `DeliveryApiClient.schedule()` (WA-9, que ya envuelve el
  `ERPBridge.schedule()` real → `ventas.direccion_entrega`/
  `fecha_entrega_programada`). Idempotente (§19) sobre
  `(order_external_id, address, delivery_date)` — pedir "programa mi
  entrega" dos veces con la misma dirección no dispara dos llamadas al
  ERP. **Cuarto consumidor real** de `compute_fingerprint()` (WA-11),
  después de Pedidos/Cotizaciones/Pagos.

## Reintento tras fallo — cubierto explícitamente, no dejado como gap

`BusinessOperationIdempotencyRecord.complete()`/`.fail()` (WA-10) solo
aceptan transicionar desde `PENDING`; como `fingerprint` es `UNIQUE`, no se
puede crear un segundo registro para el mismo intento. Este servicio
reactiva el registro existente a `PENDING` antes de reintentar cuando el
intento previo terminó en `FAILED`, en vez de fallar al reintentar (que es
lo que habría pasado con una implementación ingenua). Verificado con un
test dedicado (`test_retry_after_failure_succeeds_and_is_not_deduplicated`)
— WA-12 (`PaymentService.confirm_payment`) comparte el mismo patrón de
entidad pero no tiene un test equivalente; se documenta la diferencia en
el docstring del servicio, no se modifica WA-12 (fuera de alcance).

Cada intento deja su propia fila `DeliveryRequest` (es un rastro, no una
fila editada in-place) — un reintento tras `FAILED` crea una fila nueva en
vez de reabrir una terminal (`mark_scheduled`/`mark_failed` rechazan
reabrir, mismo invariante que `OrderDraft`/`QuoteDraft`).

CompositionRoot: +2 servicios (`delivery_requests`, `delivery_request_service`)
— `REQUIRED_SERVICES` pasó de 27 a 29.

## Tests

31 tests nuevos: `test_delivery_request_entity.py` (9), 
`test_sqlite_delivery_request_repository.py` (5), 
`test_delivery_request_service.py` (6 — incluida deduplicación real,
dirección distinta no deduplicada, fallo del ERP marca `FAILED`, reintento
tras fallo SÍ programa y no se reporta deduplicado), accessors de
`CompositionRoot` (+2), bump de conteo de tablas en `test_whatsapp_schema.py`
(16→17) + test de migración 246.

Suite completa: **567 passed, 11 failed** (mismos preexistentes desde
WA-1, `DummyParser.matcher` — no relacionados).

## Siguiente fase

WA-14 (Clientes y consentimiento) — reutiliza `customer_consents`
(CRM-9), tabla y repositorio ya reales y en producción del lado ERP; no
se inventa un segundo modelo de consentimiento del lado WhatsApp.
