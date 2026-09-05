# WA-12 — Pagos (canal WhatsApp)

Ejecutado: 2026-09-01. §38-39 y §19 del prompt maestro. Cierra el batch
WA-6..WA-12 pedido en esta sesión.

## Qué se construyó

- `domain/whatsapp/payment_provider_ports.py::PaymentProviderGateway` —
  puerto **separado** de `erp_ports.py::PaymentsApiClient` (WA-9) a
  propósito: son dos sistemas externos distintos. `PaymentsApiClient`
  habla con el ERP (`anticipos`/`ventas`); este puerto habla con
  MercadoPago (generar el link real). Mismo criterio de separación que
  `WhatsAppProviderGateway` (mensajería, WA-5) vs los clientes ERP.
- `infrastructure/providers/mercadopago/gateway.py::MercadoPagoGateway` —
  **Link** (§38): implementación real de `POST /checkout/preferences`.
- `application/payment_service.py::PaymentService`:
  - **Link** — `create_payment_link()`, arma `external_reference` como
    `{order_external_id}:{customer_phone}` (misma convención que el
    flujo legacy en vivo).
  - **Status** — `get_order_payment_status()` **reutiliza**
    `OrdersApiClient.get_status()` (WA-9) — `ERPBridge` no expone ninguna
    consulta de "estado de anticipo" propia; el estado real ya es el de
    la orden (`pendiente_wa`→`confirmada`). No se inventó un segundo
    concepto de estado que duplicara el que ya existe.
  - **Confirmation** — `register_advance()`/`confirm_payment()`, delegan
    en `PaymentsApiClient` (WA-9). WhatsApp nunca calcula el anticipo ni
    confirma un pago por su cuenta (§38).
  - **Duplicate webhook** (§19) — `confirm_payment()` es idempotente
    sobre `payment_reference` (el ID real de pago del proveedor), no
    sobre el pedido completo: dos entregas del mismo evento de webhook no
    confirman el pago dos veces. Reutiliza
    `compute_fingerprint()` (WA-11) — tercer consumidor del mismo
    algoritmo compartido, ninguno inventado de nuevo.

## Decisión de alcance explícita — no se tocó `flows/pago_flow.py`

`flows/pago_flow.py::_generar_link_pago` ya tiene su propia llamada real
al mismo endpoint de MercadoPago — es la ruta en vivo hoy. A diferencia de
`messaging/sender.py` (WA-5), donde extraer un helper compartido fue
seguro porque existían tests reales que confirmaban cero regresión,
`pago_flow.py` **no tiene ninguna cobertura de test en este árbol**
(verificado antes de decidir). Refactorizarlo para compartir código con
el nuevo gateway sin esa red de pruebas habría sido más riesgoso que el
beneficio de evitar la duplicación — se documenta como una duplicación
real y deliberada, candidata a consolidarse en una fase posterior que
primero le dé cobertura de test a ese flujo específico. No se oculta:
hoy existen dos implementaciones reales de "crear preferencia de
MercadoPago" en el árbol.

## Consumidor real, no solo contrato

A diferencia de "Status" (que reutiliza WA-9 sin nada nuevo), "Duplicate
webhook" prueba el patrón de idempotencia de negocio en su TERCER caso de
uso real (Pedidos → Cotizaciones → Pagos), cada uno con una dimensión de
fingerprint distinta pero el mismo algoritmo:

| Caso de uso | Fingerprint sobre |
|---|---|
| `OrderDraftService.confirm()` (WA-10) | contenido del carrito |
| `QuoteDraftService.create_quote()` (WA-11) | contenido del carrito |
| `QuoteDraftService.accept()` (WA-11) | `quote_external_id` |
| `PaymentService.confirm_payment()` (WA-12) | `order_external_id` + `payment_reference` |

CompositionRoot: +2 servicios (`payment_provider`, `payment_service`) —
`REQUIRED_SERVICES` pasó de 25 a 27.

## Tests

44 tests nuevos, todos en verde: `test_mercadopago_gateway.py` (5 — éxito,
token ausente, status no exitoso, respuesta sin `init_point`, payload
correcto incluida la expiración de 24h), `test_payment_service.py` (10 —
incluida la deduplicación real de doble entrega de webhook, referencia de
pago distinta NO se deduplica, fallo del ERP marca el registro `FAILED`
sin bloquear un reintento futuro), accessors de `CompositionRoot` (+2).

Suite completa: **543 passed, 11 failed** (mismos preexistentes desde
WA-1). Smoke test real: `TestClient` contra `main.py`, `/health` 200,
`root.payment_service`/`root.payment_provider` confirmados como las
clases reales.

## Estado del canal tras WA-1..WA-12

Seguridad (WA-1), dominio+esquema+bootstrap (WA-2/3/4), Provider Gateway
(WA-5), Webhook+Inbox (WA-6), Conversation Engine (WA-7), Intent
Resolution (WA-8), ERP Contracts (WA-9), y los tres flujos de negocio
reales — Pedidos (WA-10), Cotizaciones (WA-11), Pagos (WA-12) — existen,
están probados (543 tests de esta iniciativa) y verificados contra un
arranque real de `main.py`. **Nada de esto está conectado todavía al
webhook en vivo** (`webhook/whatsapp.py` sigue procesando síncronamente
vía `MessageRouter`/flows/) — es la pieza que falta para que este trabajo
deje de ser "nuevo en paralelo" y se vuelva el camino real. Fuera de
alcance de esta sesión: WA-13 en adelante (Delivery, Clientes/
consentimiento, Fidelidad, Handoff, Outbound Dispatcher, Notificaciones,
UI, Observabilidad, eliminación de legacy), y la decisión de producto
pendiente sobre qué hacer con el stack legacy ERP-embedded y Rasa
(diferida a WA-21 por decisión del usuario en WA-9).
