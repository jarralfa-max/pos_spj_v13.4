# WA-10 — Pedidos (canal WhatsApp)

Ejecutado: 2026-09-01. §34-36 y §19 del prompt maestro. Primer flujo de
negocio real construido sobre WA-1..9: el carrito conversacional
(`OrderDraft`, dominio nuevo) hasta la confirmación de un pedido real vía
`OrdersApiClient` (WA-9), con idempotencia de negocio genuina.

## Qué se construyó

- `domain/whatsapp/entities/order_draft.py::OrderDraft`/`OrderDraftLine`
  — el carrito conversacional. §34 es explícito: "el draft conversacional
  no es el pedido canónico" — vive y muere en el canal;
  `OrdersApiClient.create()` es lo único que produce un pedido real.
  Máquina de estados propia (BUILDING→AWAITING_CONFIRMATION→CONFIRMED, o
  →CANCELLED) con el mismo criterio "terminal no se edita" ya establecido
  en WA-2/WA-6.
- `domain/whatsapp/entities/business_operation.py::BusinessOperationIdempotencyRecord`
  — primer consumidor real de `whatsapp_business_operation_idempotency`
  (tabla creada en WA-3, migración 243, sin repositorio hasta ahora).
- Migración **244** (nueva) agrega `whatsapp_order_drafts`/
  `whatsapp_order_draft_lines` al esquema del canal (reutiliza
  `create_whatsapp_schema()` de la 243, no crea un módulo nuevo).
- `application/order_draft_service.py::OrderDraftService`:
  - **Draft** — `start_draft()`.
  - **Product selection** — `add_product_by_search()` usa
    `CatalogApiClient.search()` (WA-9, `ProductMatcher` real) y agrega la
    primera coincidencia; desambiguar entre varias es capa conversacional
    (WA-7/8), no de este servicio.
  - **Quantity** — cantidad numérica + unidad tal como la reporta el
    catálogo (kg/pieza/...). El flujo completo de ajuste de peso
    post-pesaje con aprobación del cliente (§36) queda **explícitamente
    fuera de esta fase** — no estaba en el checklist literal de WA-10 y
    merece su propio tratamiento, no una implementación apurada.
  - **Delivery method** — `set_delivery_method()` (PICKUP/DELIVERY).
  - **Confirmation + Idempotency** — `confirm()`: calcula un fingerprint
    determinístico sobre CONTENIDO (`conversation_id` + líneas ordenadas +
    método de entrega — nunca sobre el texto del mensaje que lo disparó),
    consulta `whatsapp_business_operation_idempotency` por ese
    fingerprint; si ya existe con resultado, retorna el pedido existente
    (`deduplicated=True`) sin llamar a `OrdersApiClient.create()` de
    nuevo; si no, crea el registro `PENDING`, llama a Orders, y lo marca
    `COMPLETED`/`FAILED` según el resultado.
- CompositionRoot: +9 servicios (2 repositorios, 6 clientes ERP ya
  contados en WA-9, `OrderDraftService`) — `REQUIRED_SERVICES` pasó de 20
  a 23.

## El caso real que prueba la idempotencia

§19 da el ejemplo exacto: "confirmar pedido" y "sí, confirmar" son dos
mensajes distintos para la MISMA acción. `test_second_confirm_attempt_with_same_content_is_deduplicated`
reproduce esto de la forma más realista posible sin tener aún el
motor conversacional completo conectado (WA-7/8 no persisten el
`OrderDraft` como parte de su propio ciclo todavía): construye un
`OrderDraft` **nuevo** con el mismo `conversation_id`+líneas+método de
entrega (la reconstrucción que un canal real haría si el cliente repite
la confirmación) y confirma dos veces — la segunda vez, `orders.create()`
nunca se vuelve a llamar; ambos intentos devuelven el mismo
`order.external_id`. Un tercer test confirma el caso contrario:
contenido de carrito distinto sí produce dos pedidos distintos, no una
falsa colisión.

## Tests

65 tests nuevos, todos en verde: `test_order_draft_entity.py` (19 —
máquina de estados, líneas, total), `test_business_operation_entity.py`
(8), `test_sqlite_order_draft_and_idempotency_repositories.py` (8 —
incluida la restricción `UNIQUE(fingerprint)` real), `test_order_draft_service.py`
(11 — el flujo completo, incluida la deduplicación real y el caso de
fallo de creación de pedido dejando el registro de idempotencia en
`FAILED` sin marcar el draft como confirmado), accessors de
`CompositionRoot` (+3). Dos tests preexistentes de `test_whatsapp_schema.py`
se actualizaron (conteo de tablas 12→14, "última migración" ya no es la
243) — regresiones propias de esta fase, corregidas en la misma pasada,
no preexistentes del proyecto.

Suite completa: **492 passed, 11 failed** (mismos preexistentes desde
WA-1). Smoke test real: bootstrap desde cero con las 244 migraciones,
`TestClient` contra `main.py`, `/health` 200, y
`root.order_draft_service` confirmado como la clase real.

## Siguiente fase

WA-11 — Cotizaciones: mismo patrón que Pedidos (capturar → `QuotesApiClient.create()`
→ aceptar/rechazar → convertir a pedido vía `QuotesApiClient.convert_to_order()`,
ya construido en WA-9) — reutilizará `OrderDraft`/fingerprint/idempotencia
donde tenga sentido en vez de duplicar el patrón desde cero.
