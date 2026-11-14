# Mercado Pago — Modelo de datos (DATA_MODEL)

- **Ítem:** SDLC-PAY-001 · **Fecha:** 2026-11-09
- **Contexto:** [TRD](MERCADO_PAGO_INTEGRATION_TRD.md)
- **Reglas:**
  - identidades internas UUIDv7 (`backend/shared/ids.py`);
  - importes Decimal guardados como TEXT;
  - los identificadores de Mercado Pago se guardan tal como los da el proveedor;
  - toda tabla nueva entra por una migración registrada en `migrations/engine.py`.
- **Propuesto:** las tablas nuevas de §2 son una propuesta. Se diseñan en el spec de su ítem.

## 1. Lo que ya existe y se reutiliza

| Tabla | Contexto | Uso para MP | Cambio en `fix/lote-4` |
|---|---|---|---|
| `sale_payments` | Ventas | El pago de la venta (`method=MERCADO_PAGO`, `reference`) | Índice único parcial `uq_sale_payments_processor_reference` (método + `UPPER(TRIM(reference))`, MP/tarjeta/transferencia), migración 384 |
| `sale_payment_voids` | Ventas | Rastro de pagos anulados; su referencia queda libre | — |
| `payment_records` / `payment_allocations` | Caja | Liquidación del cobro; `external_reference` con `UNIQUE(payment_record_id, method_type, external_reference)` | Una asignación por pago electrónico con su referencia (PAY-003) |
| `cash_refund_executions` | Caja | Reembolsos | Sin cambio: PAY-006 bloqueado |
| `cash_cuts.snapshot_json` | Caja | Corte X/Z | Claves `payment.<MEDIO>.count/gross`, `payment.sales`, `payment.mixed_sales`, `refund.electronic.*` (PAY-005) |
| `treasury_accounts` | Finanzas | **Una** cuenta `PAYMENT_PROCESSOR`, espejo 1115 | Renombrada «Procesadores de pago (Mercado Pago y tarjetas)», migración 385 |
| `journal_lines.description` | Finanzas | Lleva `ref <operación>` en la línea del procesador | PAY-003 |
| `workstation_device_assignments` | Dispositivos | Terminal Point por estación (`AssignmentRole.PAYMENT_TERMINAL`) | — (PAY-012) |
| `workstations` | Dispositivos | Fuente canónica de terminal (decisión SDLC-ARQ-TERM-001) | — |

## 2. Tablas nuevas propuestas

### `payment_intents` (PAY-007)

| Campo | Tipo | Nota |
|---|---|---|
| `id` | TEXT PK UUIDv7 | También es el `external_reference` hacia MP |
| `operation_id` | TEXT UNIQUE | Idempotencia por clic (SDLC-ARQ-IDEM-001) |
| `idempotency_key` | TEXT UNIQUE | Se manda como `X-Idempotency-Key`. Estable por intención: un reintento usa la misma |
| `source_type`, `source_id` | TEXT | `SALE` o `ORDER` y su id. Una intención viva por fuente: índice parcial sobre estados no finales |
| `channel` | TEXT | `POS_POINT`, `POS_QR`, `LINK`, `WHATSAPP` |
| `branch_id`, `workstation_id`, `terminal_device_id` | TEXT | Ámbito y terminal |
| `amount`, `currency_code` | TEXT | Importe congelado; Decimal |
| `status` | TEXT | §3 |
| `provider`, `provider_order_id`, `provider_payment_id` | TEXT | Ids externos tal cual |
| `status_detail` | TEXT | Último detalle externo, sanitizado |
| `created_by`, `created_at`, `updated_at`, `version` | | Concurrencia optimista |

Índice único parcial `(terminal_device_id)` sobre los estados `SUBMITTED` y `PROCESSING`: una terminal,
una orden en curso (PAY-012).

### `payment_provider_events` (PAY-010)

Inbox durable de notificaciones.

- **Columnas:** `id`, `provider`, `notification_id` UNIQUE, `topic`, `resource_id`, `received_at`,
  `signature_valid`, `payload_json` sin secretos, `status`, `attempts`, `next_attempt_at`, `last_error`.
- **`status`:** `RECEIVED`, `PROCESSED`, `IGNORED` o `DEAD`.

### `payment_refund_requests` (PAY-006/020)

Pendiente de las decisiones contables de PAY-006.

- **Columnas:** `id`, `sale_id`, `source`, `source_id`, `method`, `amount`, `original_reference`,
  `refund_reference`, `status`, `requested_by`, `requested_at`, `resolved_by`, `resolved_at`, `reason`,
  `operation_id`.
- **`source`:** `RETURN`, `REVERSAL`, `VOID` o `CANCEL`.
- **`status`:** `REQUESTED`, `CONFIRMED` o `REJECTED`.

### `processor_settlements` y `processor_settlement_lines` (PAY-019)

- Lotes importados con hash anti-duplicado: el mismo patrón que `import_bank_statement_use_case`.
- Cada línea liga la operación de MP con la `payment_allocation`.
- Estados: `CAPTURED`, `SETTLED`, `RECONCILED`, `EXCEPTION`.

## 3. Estados de `PaymentIntent` y capa anticorrupción

```
CREATED → SUBMITTED → PROCESSING → APPROVED (final, confirmado)
                    ↘            ↘ REJECTED | CANCELED | EXPIRED (finales)
           cualquier no final → UNKNOWN (timeout o respuesta perdida) → se resuelve por consulta
APPROVED → REFUNDED_PARTIAL → REFUNDED (PAY-020) ; APPROVED → CHARGED_BACK (PAY-021)
```

- Una transición sólo avanza. Un evento tardío que propone un estado anterior se registra y se ignora.
- La ACL traduce el estado de la orden de Orders API (`created`, `at_terminal`, `processed`, `canceled`,
  `expired`, `failed`, `refunded`…) y su `status_detail` a estos estados.
- **No verificado:** la lista exacta de estados de la Orders API se valida contra la documentación oficial
  vigente al construir PAY-009. Esta sesión no consultó la API.

## 4. Eventos

| Evento | Productor | Consumidores | Nota |
|---|---|---|---|
| `SALE_COMPLETED` (existente) | Ventas | Caja, Finanzas, Fidelidad, central | Desde PAY-003 lleva `payment_references: [{method, amount, reference}]`; `payments` sigue agregado por método (el central tiene PK `(sale_id, method)`) |
| `PAYMENT_INTENT_STATUS_CHANGED` (nuevo, PAY-007) | Pagos | Ventas, POS, notificaciones | Payload sin token ni datos de tarjeta |
| `PAYMENT_REFUND_CONFIRMED` (nuevo, PAY-006) | Caja o Pagos | Finanzas (asiento al confirmar) | Bloqueado |
