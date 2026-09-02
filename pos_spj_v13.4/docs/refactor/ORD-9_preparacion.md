# ORD-9 — Preparación

Fecha: 2026-08-31. Alcance: master prompt §25 (cola, asignación, inicio, artículos,
finalización).

## Qué se construyó

- `PreparationStatus` enum (PENDING/ASSIGNED/IN_PROGRESS/PARTIALLY_PREPARED/
  PENDING_WEIGHT/PENDING_CUSTOMER_APPROVAL/READY/CANCELLED), independiente de
  `FulfillmentStatus` (que solo ve PENDING/PREPARING/READY).
- `OrderPreparationPolicy` (tabla de transiciones, mismo estilo que las anteriores).
- Campos nuevos en `CustomerOrder`: `preparation_status`, `assigned_to_user_id`,
  `station_id`, `preparation_started_at`, `preparation_completed_at`. Métodos:
  `assign_preparation()`, `start_preparation()`, `complete_preparation()`,
  `cancel_preparation()`.
- `CustomerOrderLine.record_prepared_amount()` — registra `prepared_quantity`/
  `prepared_weight` y marca la línea `PREPARED`. Deliberadamente NUNCA escribe
  `final_*` — esa decisión pertenece a la política de tolerancia/aprobación del
  cliente (ORD-10/ORD-11).
- Casos de uso: `AssignPreparationUseCase`, `StartPreparationUseCase`,
  `RecordPreparedLineUseCase`, `CompletePreparationUseCase` — reutilizan
  `PREPARATION_ASSIGN`/`PREPARATION_START`/`WEIGHT_CAPTURE`/`PREPARATION_COMPLETE`
  de ORD-1, sin permisos nuevos.

## Decisiones

- **No se construyó una entidad `OrderPreparation`/`OrderPreparationLine` separada** — a
  diferencia de la §9.3 del prompt maestro que las lista como archivos propios, este
  dominio ya modela preparación como estado adicional sobre `CustomerOrder`/
  `CustomerOrderLine` (mismo criterio que ORD-6/ORD-7: extender el agregado existente en
  vez de fragmentar en más tablas/entidades cuando el estado adicional cabe naturalmente
  en lo que ya existe).
- **`complete_preparation()` exige que TODAS las líneas estén en un estado terminal**
  (PREPARED/READY/SUBSTITUTED/REJECTED) — un pedido a medio preparar no puede marcarse
  listo; verificado explícitamente, no solo por el estado agregado.
- **`start_preparation()` NO valida disponibilidad de nuevo** — exige `fulfillment_status
  == RESERVED` (ORD-8 ya lo garantizó); no se repite la validación de stock.

## Tests

16 tests nuevos (11 dominio + 5 integración, esta última recorriendo el pipeline completo
capturar→confirmar→reservar→preparar contra ambos esquemas reales). Suite acumulada
ORD-1..9: **135/135 pasando**.

## Pendiente

- Sustituciones (§29, ORD-12) y aprobación del cliente por peso fuera de tolerancia
  (§27, ORD-11) no se construyeron — `record_prepared_amount()` siempre marca `PREPARED`
  sin evaluar tolerancia todavía.
