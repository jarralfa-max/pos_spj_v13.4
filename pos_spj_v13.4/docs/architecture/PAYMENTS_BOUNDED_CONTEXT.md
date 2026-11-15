# Payments bounded context — decisiones de diseño

## Propósito

Coordinar la intención de cobro y los adaptadores de proveedores externos sin introducir reglas de Mercado Pago en Ventas, Finanzas o la interfaz PyQt. El contexto se mantiene independiente del proveedor para que Checkout Pro, QR y Point compartan el mismo ciclo de vida.

## Límites

- `domain/payments`: identidad, canal, método, propósito, importe, moneda y transiciones de `PaymentIntent`.
- `application/payments` (siguiente fase): casos de uso, autorización de actor/sistema, coordinación de persistencia y puertos.
- `infrastructure/payments` (siguiente fase): Mercado Pago API, verificación de firma, repositorios, webhook ingress y conciliación.
- Ventas sigue siendo la autoridad de cobro aplicado a una venta: `RecordSalePaymentUseCase` registra el pago aprobado y `CheckoutSaleUseCase` es la única ruta de completar la venta.
- Finanzas sigue recibiendo `SALE_COMPLETED` mediante `finance_translator`; Payments no genera asientos contables paralelos.
- WhatsApp consume los casos de uso/API de Payments. El flujo conversacional no crea preferencias directamente.

## Identidad y seguridad

- `PaymentIntent.id` es UUIDv7 y se usa como `external_reference` opaca.
- Nunca enviar teléfono, folio comercial o datos personales en `external_reference`.
- El identificador local de idempotencia es independiente del `provider_payment_id`.
- El dominio sólo acepta confirmación después de consulta autoritativa del proveedor y verifica referencia, importe exacto y moneda.
- La restricción única del `provider_payment_id` debe implementarse en infraestructura antes de procesar webhooks en producción.
- La firma HMAC, anti-replay, límites de cuerpo y la bandeja de pagos no asignados existentes en WhatsApp deben conservarse y extraerse al adaptador común; no debilitarlos.

## Primera entrega

La primera entrega agrega únicamente los catálogos y la entidad pura `PaymentIntent`, sin I/O ni acceso a DB:
- Canales POS/WHATSAPP.
- Métodos CHECKOUT/QR/POINT.
- Propósitos FULL/DEPOSIT/BALANCE.
- Estados CREATED/PENDING/APPROVED/REJECTED/CANCELLED/EXPIRED/REFUNDED/REVIEW_REQUIRED.
- Confirmación idempotente del mismo payment_id y rechazo de una segunda operación distinta sobre la misma intención.
- Pruebas unitarias de referencia, importe, moneda, replays y transición terminal.

## Fases pendientes antes de uso real

1. Persistencia/repositorio con UUIDv7, índices únicos e idempotencia transaccional.
2. Caso de uso de creación de intent y adapter Checkout Pro común.
3. Handler de notificaciones compartido que conserve HMAC y consulte el recurso MP.
4. Integración POS QR.
5. Integración POS Point, condicionada al modelo de terminal y capacidades de cuenta.
6. Pagos parciales WhatsApp y liquidación de saldo.
7. Integración con Ventas por los casos de uso oficiales, luego conciliación de Finanzas.
8. Pruebas de integración/concurrencia y regresión en CI.

No activar feature flags de producción hasta completar las fases pendientes.
