# Mercado Pago — Flujos de aplicación (APPFLOW)

- **Ítem:** SDLC-PAY-001 · **Fecha:** 2026-11-09
- **Contexto:** [TRD](MERCADO_PAGO_INTEGRATION_TRD.md) · [ADR](MERCADO_PAGO_INTEGRATION_ADR.md)
- **Convención:** las cajas `[…]` son casos de uso; «→ outbox» es un evento en la misma transacción. Los
  estados son los del [DATA_MODEL](MERCADO_PAGO_INTEGRATION_DATA_MODEL.md) §3.

## 1. Cobro manual (vigente, contención de `fix/lote-4`)

```
F9 → PaymentDialog (MERCADO_PAGO visible con POS.pago.mercado_pago)
   → el cajero cobra fuera (app o terminal MP) y captura monto + número de operación (obligatorio)
   → payment_reference_check: formato y no repetida, ANTES de iniciar el cobro       PAY-002
   → [BeginSaleCheckout] → [RecordSalePayment] valida otra vez; índice único 384 como respaldo
   → [CheckoutSale] → outbox SALE_COMPLETED con payment_references                    PAY-003
        → Caja: una payment_allocation por pago, external_reference = la referencia
        → Finanzas: Debe 1115 (cuenta de procesadores) «… ref <operación>»            PAY-004
   → Ticket: «Ref. Mercado Pago ****1234»
Corte X/Z: «Mercado Pago (n) bruto» separado de efectivo y tarjeta                    PAY-005
```

Lo que el cobro manual **no** garantiza: que el pago exista en Mercado Pago. Esa garantía llega con los
flujos 2 a 4.

## 2. Cobro con Point Smart (objetivo, PAY-007/009/012/013)

```
[CreatePaymentIntent] sale_id, importe congelado, método MP_POINT, terminal de la estación
   valida: permiso, turno abierto, saldo pendiente, moneda; idempotente por operation_id
   → intent CREATED
[SubmitProviderOrder] PaymentProviderPort.create_order(type=point, external_reference=intent.id,
                      X-Idempotency-Key=intent.idempotency_key)
   → SUBMITTED  (un HTTP 201 NO es APPROVED)
   → terminal ocupada por otra estación → rechazo antes de llamar al proveedor
POS muestra estados (UX §2); el diálogo no bloquea la ventana
Resultado por webhook verificado (flujo 5) o por consulta (flujo 6):
   APPROVED → [ConfirmIntent] → Ventas: RecordSalePayment(reference=payment_id) → CheckoutSale
   REJECTED / CANCELED / EXPIRED → el saldo sigue pendiente; el cajero elige otro medio
Timeout o respuesta perdida → UNKNOWN: se consulta con el MISMO intent; nunca se crea otra orden
Reinicio del POS → el diálogo retoma la intención abierta de la venta (CHECKOUT_PENDING / PAYMENT_PENDING)
```

## 3. Enlace de pago y QR (PAY-014/015/025)

```
[CreatePaymentIntent] canal POS / Pedido / WhatsApp; una intención viva por venta o pedido
[SubmitProviderOrder] type=online → checkout_url con vigencia
   POS: QR en el diálogo y en el monitor del cliente (qr_matrix)
   WhatsApp: el microservicio PIDE la intención al ERP y envía el enlace; no crea preferencias propias
Confirmación asíncrona: flujos 5 y 6. Enlace vencido → EXPIRED; volver a pedir crea una intención nueva
```

## 4. Pago mixto (PAY-016)

Primero se congela el plan: efectivo X + MP Y.

- La porción electrónica se cobra primero.
- Si falla, no se registra efectivo.
- Si el efectivo se registra y la porción electrónica queda `UNKNOWN`, la venta queda en
  `PAYMENT_PENDING` hasta resolverse.

Montos en Decimal desde el `MoneyInput`, sin `float`.

## 5. Webhook (PAY-010, ADR-MP-002)

```
POST /api/v1/integrations/mercadopago/webhooks   (ruta conceptual; seguir el estándar de backend/api)
   → límite de tamaño; parsing estricto; firma x-signature con ventana de ts
   → INSERT payment_provider_events (dedup por id de notificación) → HTTP 200 sólo después del commit
worker:
   → GET de la orden o el pago en Mercado Pago (la notificación es una señal, no la verdad)
   → compara monto, moneda, collector_id (una cuenta por empresa, ADR-MP-005) y external_reference
   → aplica la transición de la intención si es hacia adelante; un evento tardío no retrocede un estado final
   → reintentos con backoff; al agotarse → revisión manual (dead-letter) con alerta
```

## 6. Conciliación por consulta (PAY-011)

Una tarea periódica toma las intenciones `SUBMITTED`, `PROCESSING` y `UNKNOWN` con antigüedad mayor a
N minutos. Por cada una:

1. Consulta la orden.
2. Aplica la misma transición que el webhook.

Cubre:

- el túnel caído;
- la PC anfitriona apagada;
- la respuesta HTTP perdida;
- el reinicio del POS.

## 7. Sin internet (PAY-017, decisión SDLC-ARQ-HYB-002)

Decisión del responsable (2026-11-02): sin internet, **Mercado Pago no**.

- El método se muestra deshabilitado con el motivo.
- No se crean órdenes ni se inventan aprobaciones.
- El efectivo sigue.
- Las intenciones `UNKNOWN` se resuelven al volver la red (flujo 6), antes de habilitar cobros nuevos en
  esa terminal.

## 8. Reembolso (PAY-006 bloqueado → PAY-020)

```
Hoy:  devolución/reverso → CashRefundExecution ORIGINAL_PAYMENT_METHOD «ejecutado» + abono inmediato a 1115
Meta: devolución/anulación/reverso → solicitud de reembolso SOLICITADO (sin asiento de salida de dinero)
      → el cajero hace el reembolso en el panel de MP y captura la referencia del reembolso
        (decisión: «cajero con su permiso y envía alerta a gerente»)
      → CONFIRMADO → asiento; o RECHAZADO → tratamiento por definir (TRD §6)
      → con API (PAY-020): RefundPayment por el puerto; confirmación por consulta o webhook
```

## 9. Cierre de caja y liquidación (PAY-005 hecho; PAY-018/019)

- **Corte Z:** bruto por medio de pago, conteo, ventas mixtas y reembolsos a medio electrónico.
- **Liquidación (PAY-019):**
  1. Se importa el reporte de MP.
  2. Cada operación se casa por `external_reference` (Caja) o por la referencia en la línea del asiento
     (Finanzas).
  3. Se asientan comisión, IVA de comisión y neto contra la cuenta de procesadores.
  4. La operación pasa de `CAPTURED` a `SETTLED` y a `RECONCILED`.
