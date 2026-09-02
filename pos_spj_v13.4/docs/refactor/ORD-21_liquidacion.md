# ORD-21 — Liquidación de repartidor

Fecha: 2026-08-31. Alcance: master prompt §46 (reconciliación de cobros pendientes de un
repartidor en una liquidación única, con flujo de revisión cuando hay diferencia).

## Qué se construyó

- `SettlementStatus` (§46, 7 estados: OPEN/PENDING_REVIEW/BALANCED/WITH_DIFFERENCE/
  APPROVED/POSTED/CLOSED) enum y `SettlementPolicy` — tabla de transiciones que separa el
  camino feliz (BALANCED → APPROVED directo) del camino con diferencia (WITH_DIFFERENCE →
  PENDING_REVIEW → APPROVED), ambos convergiendo en POSTED → CLOSED.
- `backend/domain/orders_delivery/settlement.py` — `DriverSettlement`: `create()` reúne
  una lista de `DriverCashCollection`, suma `expected_total`/`collected_total` y
  auto-resuelve BALANCED vs. WITH_DIFFERENCE según `difference` (misma idea de "una sola
  función de decisión" que `record_collection()` usó en ORD-20). `submit_for_review()`,
  `approve()`, `post()`, `close()` completan el ciclo de vida.
- `backend/application/orders_delivery/use_cases/settlement_use_cases.py` —
  `CreateDriverSettlementUseCase` (junta TODOS los `DriverCashCollection` en
  `PENDING_SETTLEMENT` del repartidor y los marca `SETTLED` en la misma transacción — nunca
  queda un cobro "pendiente de liquidar" mientras ya pertenece a una liquidación),
  `ApproveDriverSettlementUseCase`, `CloseDriverSettlementUseCase`.
- Tabla `driver_settlements` (colección de ids serializada como JSON) y
  `DriverSettlementRepository`, cableado en `OrdersDeliveryUnitOfWork`.

## Decisiones

- **Un cobro liquidado no puede volver a liquidarse** — `CreateDriverSettlementUseCase`
  consulta solo `PENDING_SETTLEMENT` y llama `collection.mark_settled()` dentro de la misma
  unidad de trabajo que crea la liquidación, evitando que dos liquidaciones reclamen el
  mismo cobro.
- **BALANCED se aprueba directo; WITH_DIFFERENCE exige revisión primero** — refleja el
  mismo patrón de "camino corto vs. camino con control adicional" que ya existía en otras
  políticas de este dominio (p. ej. sustituciones en ORD-12).

## Bug encontrado y corregido (6º de este pipeline)

`CreateDriverSettlementUseCase` emitía un segundo evento
(`DRIVER_SETTLEMENT_DIFFERENCE_DETECTED`) cuando la liquidación resultaba WITH_DIFFERENCE,
reutilizando el mismo `operation_id` del caso de uso. Eso violó la restricción
`UNIQUE(operation_id)` de `orders_delivery_outbox` (§57: un `operation_id` = una fila de
outbox). El primer intento de arreglo — sufijar el id (`f"{operation_id}-difference"`,
siguiendo el patrón de ORD-8 para reservas por línea) — rompió `delivery_event_payload()`,
que exige un UUIDv7 canónico real vía `validate_uuidv7()` (a diferencia del `operation_id`
de Inventario, que no impone ese formato). Corrección definitiva: el segundo evento es una
notificación distinta disparada por la misma llamada, no la misma operación idempotente, así
que recibe su propio `new_uuid()` en vez de derivar del `operation_id` original.

## Tests

15 tests nuevos (8 dominio + 7 integración, incluyendo los dos que expusieron el bug de
UUIDv7 antes de la corrección). Suite acumulada ORD-1..21 de orders_delivery: **309/309
pasando** (unitarios + integración, `tests/unit/test_orders_delivery_*.py` +
`tests/integration/test_orders_delivery_*.py`).

## Pendiente

- Disputa de liquidación (`dispute()`/reapertura tras CLOSED) — fuera del alcance mínimo de
  §46; los estados ya existen en `SettlementStatus` para una fase futura si se requiere.
- Continúa ORD-22 (Ventas y Finanzas: proyección de Sale, estado de pago, caja, crédito,
  reembolso).
