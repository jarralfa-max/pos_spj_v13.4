# EVENT CATALOG — SALES (FASE 8)

Fecha: 2026-05-27  
Estado: catálogo vivo (no destructivo, sin eliminar eventos legacy).

## Convenciones
- **Canónico**: nombre recomendado objetivo.
- **Alias legacy**: nombres existentes equivalentes.
- **Tx**: se emite dentro de transacción/SAVEPOINT.
- **Post-commit**: se emite fuera de tx crítica.
- **Strict**: `publish(strict=True)` (handler puede hacer fallar operación).
- **Idempotency key**: `operation_id` en payload o derivado.

---

## 1) SALE_ITEMS_PROCESS
- **Canónico**: `SALE_ITEMS_PROCESS`
- **Alias legacy**: `sale_items_process` (domain event string)
- **Publisher**: `SalesService.execute_sale()`
- **Consumers**:
  - `SaleInventoryHandler`
  - `SaleFinanceHandler`
  - `CreditSaleFinanceHandler`
- **Cuándo se emite**: después de persistir cabecera+líneas de venta.
- **Tx/Post-commit**: **Tx (SAVEPOINT)**.
- **Strict**: **Sí** (`strict=True`).
- **Puede fallar operación**: **Sí**.
- **Payload schema (actual)**:
  - `sale_id`, `folio`, `branch_id|sucursal_id`, `total`, `user|usuario`,
  - `client_id|cliente_id`, `payment_method`, `items[]`, `operation_id`.
- **Idempotency key**: `operation_id`.
- **Tablas afectadas (consumidores)**:
  - `inventory_movements`, `movimientos_caja`, `accounts_receivable|cuentas_por_cobrar` (según handler).
- **Riesgo de duplicidad**:
  - reintento sin idempotencia en handlers puede duplicar movimientos.

---

## 2) SALE_COMPLETED
- **Canónico**: `SALE_COMPLETED`
- **Alias legacy**: `VENTA_COMPLETADA`, `SALE_CREATED`.
- **Publisher**: `SalesService.execute_sale()`.
- **Consumers**:
  - `_sync_venta`, `_loyalty_venta` (guardado por bandera), `_audit_venta`, `_treasury_venta`, `SaleTraceHandler`.
- **Cuándo se emite**: tras `RELEASE SAVEPOINT`.
- **Tx/Post-commit**: **Post-commit in-memory** (+ outbox persist best-effort).
- **Strict**: No.
- **Puede fallar operación**: No.
- **Payload schema (actual)**:
  - `venta_id`, `folio`, `branch_id|sucursal_id`, `total`, `usuario`, `cliente_id`, `payment_method`,
  - `loyalty_already_processed`, `loyalty_snapshot`, `operation_id` (en payload enriquecido/outbox).
- **Idempotency key**: `operation_id`.
- **Tablas afectadas**: indirectas por handlers (`financial_event_log`, `treasury_*`, trazas).
- **Riesgo de duplicidad**:
  - lealtad si no se respeta `loyalty_already_processed` + policy idempotente.

---

## 3) SALE_CANCELLED
- **Canónico**: `SALE_CANCELLED`
- **Alias legacy**: `VENTA_CANCELADA`.
- **Publisher**: `SalesReversalService.cancel_sale()`.
- **Consumers**:
  - `SaleCancelledFinanceHandler` y trazas financieras.
- **Cuándo se emite**: al finalizar cancelación compensatoria.
- **Tx/Post-commit**: Post-commit async.
- **Strict**: No.
- **Puede fallar operación**: No (venta ya cancelada).
- **Payload schema (actual base)**:
  - `venta_id`, `folio`, `total`, `operation_id`, metadatos de usuario/sucursal.
- **Idempotency key**: `operation_id`.
- **Tablas afectadas**: `journal_entries|financial_event_log|treasury_*` por handlers.
- **Riesgo**: doble compensación si se reprocesa sin guardia idempotente.

---

## 4) SALE_REFUNDED
- **Canónico**: `SALE_REFUNDED`
- **Alias legacy**: eventos refund internos de reversa (`VENTA_REFUND*`).
- **Publisher**: `SalesReversalService.refund_items()`.
- **Consumers**: finanzas/inventario/auditoría (según wiring).
- **Cuándo**: en devolución parcial/total.
- **Tx/Post-commit**: operación compensatoria atómica + evento post.
- **Strict**: No.
- **Puede fallar operación**: evento no; operación sí durante tx.
- **Payload mínimo esperado**:
  - `sale_id`, `refund_ids`, `amount`, `operation_id`, `items`.
- **Idempotency key**: `operation_id`.
- **Tablas**: `sale_refunds`, `inventory_movements`, `movimientos_caja`.

---

## 5) SALE_CREDIT_NOTE_ISSUED
- **Canónico**: `SALE_CREDIT_NOTE_ISSUED`
- **Alias legacy**: eventos de `credit_notes` en reversa.
- **Publisher**: `SalesReversalService.issue_credit_note()`.
- **Consumers**: finanzas/GL/trazas.
- **Cuándo**: emisión de nota de crédito.
- **Tx/Post-commit**: operación atómica + notificación post.
- **Strict**: No.
- **Payload mínimo**:
  - `sale_id`, `credit_note_id`, `amount`, `reason`, `operation_id`.
- **Tablas**: `credit_notes`, `movimientos_caja`, `journal_entries`.

---

## 6) LOYALTY_POINTS_REDEEMED
- **Canónico**: `LOYALTY_POINTS_REDEEMED`
- **Alias legacy**: `LOYALTY_POINTS_REDEEMED` (event_bus upper), `loyalty_points_redeemed` (domain lower).
- **Publisher**: `LoyaltyService` (invocado desde `SaleLoyaltyPolicy.apply_redemption`).
- **Consumers**: handlers financieros de lealtad + trazas.
- **Cuándo**: canje aplicado.
- **Tx/Post-commit**: idealmente dentro de tx de venta (canje atómico).
- **Strict**: depende del publisher; normalmente no-strict async para downstream.
- **Payload**:
  - `cliente_id`, `puntos`, `venta_id`, `usuario|cajero_id`, `operation_id`.
- **Idempotency key**: `operation_id:redeem`.
- **Riesgo**: doble canje mitigado con `SaleLoyaltyPolicy`.

---

## 7) LOYALTY_POINTS_EARNED
- **Canónico**: `LOYALTY_POINTS_EARNED`
- **Alias legacy**: `LOYALTY_POINTS_EARNED` / `loyalty_points_earned`.
- **Publisher**: `LoyaltyService` (desde `SaleLoyaltyPolicy.earn_points`).
- **Consumers**: finanzas de lealtad + trazas.
- **Cuándo**: acreditación postventa.
- **Tx/Post-commit**: post-commit.
- **Strict**: No.
- **Payload**: `cliente_id`, `puntos`, `venta_id`, `usuario`, `operation_id`.
- **Idempotency key**: `operation_id:earn`.

---

## 8) STOCK_RESERVED
- **Canónico**: `STOCK_RESERVED`
- **Alias legacy**: `STOCK_RESERVADO`.
- **Publisher**: `modulos/ventas.py` al suspender venta.
- **Consumers**: auditoría/stock reservation flows.
- **Cuándo**: suspensión de venta.
- **Tx/Post-commit**: fuera de tx de venta final.
- **Strict**: No.
- **Payload**: `venta_id`, `reserva_id`, `sucursal_id`.

## 9) STOCK_RESERVATION_RELEASED
- **Canónico**: `STOCK_RESERVATION_RELEASED`
- **Alias legacy**: `STOCK_RESERVA_LIBERADA`.
- **Publisher**: `modulos/ventas.py` al cancelar reserva/suspensión.
- **Payload**: `reserva_id`, `sucursal_id`.

## 10) STOCK_RESERVATION_CONFIRMED
- **Canónico**: `STOCK_RESERVATION_CONFIRMED`
- **Alias legacy**: `STOCK_DESCONTADO_RESERVA` (+ `VENTA_CONFIRMADA_RESERVA`).
- **Publisher**: `modulos/ventas.py` al confirmar venta reanudada.
- **Payload**: `reserva_id`, `sucursal_id`, `folio`.

---

## 11) PAYMENT_CONFIRMED
- **Canónico**: `PAYMENT_CONFIRMED`
- **Alias legacy**: `payment_confirmed`.
- **Publisher**: servicios financieros/CxC.
- **Consumers**: `PaymentTraceHandler`.
- **Cuándo**: confirmación de cobro.
- **Tx/Post-commit**: post-commit.
- **Payload**: `payment_id|document_id`, `amount`, `cliente|tercero`, `operation_id`.

## 12) DELIVERY_PAYMENT_CONFIRMED
- **Canónico**: `DELIVERY_PAYMENT_CONFIRMED`
- **Alias legacy**: `delivery_payment_confirmed`.
- **Publisher**: delivery/finance integration.
- **Consumers**: `DeliveryPaymentHandler` en trazas.
- **Payload**: `order_id`, `amount`, `payment_ref`, `operation_id`.

---

## Decisiones de deprecación (propuesta)
1. Mantener `VENTA_COMPLETADA` como runtime actual y documentar `SALE_COMPLETED` como nombre canónico objetivo.
2. Mantener eventos de reservas en español por compatibilidad, introducir aliases canónicos en inglés en fase posterior.
3. No eliminar eventos legacy en esta fase.

## Riesgos de duplicidad transversales
- Eventos equivalentes ES/EN/lowercase en coexistencia.
- Reintentos sin idempotencia en handlers financieros.
- Doble fidelidad (acreditación en servicio + handler) mitigado por:
  - `loyalty_already_processed` en `VENTA_COMPLETADA`.
  - `SaleLoyaltyPolicy` con `operation_id` por operación (`redeem/earn/reverse`).

## Recomendación operativa
- Estándar mínimo de payload para todo evento de ventas:
  - `operation_id` (obligatorio)
  - `sale_id|venta_id`
  - `branch_id|sucursal_id`
  - `usuario`
  - `timestamp`
- Para fases siguientes: validar schema por evento con contrato explícito (pydantic/dataclass).
