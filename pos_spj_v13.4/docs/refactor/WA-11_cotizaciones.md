# WA-11 — Cotizaciones (canal WhatsApp)

Ejecutado: 2026-09-01. §37 y §19 del prompt maestro. Mismo patrón que
Pedidos (WA-10), con la diferencia real que §37 exige: una cotización se
CREA en el ERP (folio+vigencia) y solo DESPUÉS se acepta/rechaza — dos
pasos, no uno.

## Qué se construyó

- `domain/whatsapp/entities/quote_draft.py::QuoteDraft` — reutiliza
  `OrderDraftLine` (WA-10) en vez de duplicar una línea idéntica; nada en
  esa forma es específico de pedidos. Máquina de estados propia:
  CAPTURING→CREATED→ACCEPTED/REJECTED, o →EXPIRED. `accept()`/`reject()`
  exigen `CREATED` explícitamente — `QuoteDraftNotYetCreatedError` si se
  intenta antes de que el ERP haya emitido folio real.
- Migración **245** (nueva) agrega `whatsapp_quote_drafts`/
  `whatsapp_quote_draft_lines`, reutilizando `create_whatsapp_schema()`
  (mismo módulo de 243/244).
- `application/idempotency_fingerprint.py::compute_fingerprint()` —
  extraído de `order_draft_service.py` (WA-10) a un módulo compartido, sin
  cambiar el algoritmo (mismo hash para las mismas entradas, verificado
  con la suite de WA-10 sin tocar). Un solo cálculo de fingerprint para
  todo el canal, no uno por caso de uso.
- `application/quote_draft_service.py::QuoteDraftService`:
  - **Capture** — `start_draft()`/`add_product_by_search()` (idéntico
    patrón a `OrderDraftService`, mismo `CatalogApiClient`).
  - **Create** — `create_quote()`: idempotente sobre contenido
    (`conversation_id`+líneas, igual criterio que Pedidos), llama a
    `QuotesApiClient.create()` (WA-9), y ahora `QuoteRef` trae
    `folio`/`valid_until` reales del ERP (campos agregados a WA-9 en esta
    fase — nombres de columna del lado ERP leídos de forma tolerante, no
    verificados de forma independiente contra el código real de
    `ERPBridge`, documentado como tal).
  - **Accept** — `accept()`: idempotente sobre `quote_external_id` (no
    sobre contenido — aceptar es una acción por cotización específica,
    no por carrito), llama **siempre** a
    `QuotesApiClient.convert_to_order()` — nunca SQL directo (§37 lo pide
    explícitamente, verificado con test dedicado).
  - **Reject** — `reject()`, sin llamada al ERP (una cotización rechazada
    no necesita que el ERP haga nada).
- CompositionRoot: +2 servicios (`quote_drafts`, `quote_draft_service`) —
  `REQUIRED_SERVICES` pasó de 23 a 25.

## Tests

79 tests nuevos, todos en verde: `test_quote_draft_entity.py` (16),
`test_sqlite_quote_draft_repository.py` (4), `test_quote_draft_service.py`
(15 — incluida la deduplicación real de `create_quote()` con una
reconstrucción independiente del mismo contenido, la deduplicación de
`accept()` llamado dos veces sobre el mismo draft, y el test explícito de
que aceptar nunca toca SQL directo), accessors de `CompositionRoot` (+2).
Dos tests preexistentes de `test_whatsapp_schema.py` actualizados
(conteo de tablas 14→16) — mismo tipo de ajuste que en WA-10, corregido en
la misma pasada.

Suite completa: **528 passed, 11 failed** (mismos preexistentes desde
WA-1). Smoke test real: bootstrap desde cero con las 245 migraciones,
`/health` 200, `root.quote_draft_service` confirmado como la clase real.

## Siguiente fase

WA-12 — Pagos: Link, Status, Confirmation, Duplicate webhook. El webhook
de MercadoPago (WA-1 ya lo aseguró: firma HMAC + ventana de replay) es el
consumidor real que falta conectar a `PaymentsApiClient.confirm_payment()`
(WA-9) con la misma disciplina de idempotencia que Pedidos/Cotizaciones.
