# ORD-20 — Pagos contra entrega

Fecha: 2026-08-31. Alcance: master prompt §44-45 (solicitud de cobro, efectivo, terminal,
transferencia).

## Qué se construyó

- `CollectionPaymentMethod` (§44, 7 métodos: CASH/CARD_TERMINAL/TRANSFER/PAYMENT_LINK/
  MIXED/CREDIT/PREPAID) y `CollectionStatus` (§45, 7 estados) enums.
- `backend/domain/orders_delivery/cash_collection.py` — `DriverCashCollection`:
  `record_collection()` resuelve automáticamente COLLECTED/PARTIALLY_COLLECTED/FAILED
  según el monto cobrado vs. esperado (una sola función de decisión, nunca si/else
  repetido en cada caso de uso). `dispute()`/`mark_pending_settlement()`/`mark_settled()`
  ya construidos para que ORD-21 (Liquidación) los reutilice.
- `CreateCashCollectionRequestUseCase` (idempotente por `delivery_job_id`, exige
  repartidor ya asignado), `RecordCashCollectionUseCase`.
- Agregados 4 eventos de `DeliveryEvents` que faltaban del catálogo §59 original:
  `CASH_COLLECTION_RECORDED`, `DRIVER_SETTLEMENT_CREATED`,
  `DRIVER_SETTLEMENT_DIFFERENCE_DETECTED`, `DRIVER_SETTLEMENT_CLOSED` — los tres últimos
  se usarán en ORD-21, agregados ahora porque estaban en la lista original del prompt
  maestro y se habían pasado por alto al construir `events.py` en ORD-15.

## Decisiones

- **`CashCollectionRequest` es explícito, no inferido** — se crea con su propio caso de
  uso (normalmente justo después del despacho si `DeliveryJob.cash_to_collect > 0`), nunca
  se asume silenciosamente. Esta fase no modificó `DispatchDeliveryJobUseCase` (ORD-18)
  para auto-crearlo; esa integración queda como una decisión de orquestación futura, no
  bloquea esta fase.
- **Reintentar tras `FAILED` está permitido** — `record_collection()` acepta un nuevo
  registro desde `EXPECTED` o `FAILED`, pero NO desde `COLLECTED`/`PARTIALLY_COLLECTED`
  (evita sobrescribir un cobro ya exitoso sin pasar por `dispute()` primero).
- **Liquidación agregada de múltiples cobros es ORD-21**, no esta fase — `DriverCashCollection`
  solo modela UN cobro de UNA entrega.

## Tests

17 tests nuevos (10 dominio + 7 integración). Suite acumulada ORD-1..20: **299/299
pasando** (205 unitarios + 94 de integración, verificados por separado).

## Pendiente

- Liquidación de repartidor (ORD-21) — reconciliar múltiples `DriverCashCollection` por
  repartidor, con los estados `PENDING_SETTLEMENT`/`SETTLED`/`DISPUTED` ya listos para
  usarse.
- Integración automática despacho→solicitud de cobro (actualmente manual/explícita).
