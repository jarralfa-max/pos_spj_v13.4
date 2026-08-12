# PROC-2 — Dominio base: Procesamiento Cárnico

Estado: **DONE** (núcleo productivo de 7 entidades + políticas + eventos; sin
infraestructura, sin Use Cases, sin UI)

## Alcance

El "núcleo productivo" que el prompt maestro define como canónico en su propio §1
("Principio Rector"): `ProcessingOrder`, `ProcessingBatch`, `ProcessExecution`,
`MaterialConsumption`, `ProcessOutput`, `ProcessWeighing`, `YieldReconciliation`.
Todo lo demás (`MaterialRequirement`, work centers/recursos, incidencias,
reprocesos, empaque/etiquetas, genealogía, sacrificio) es una fase posterior — ver
`PROC-0_legacy_audit.md` para el roadmap completo.

## Componentes creados

```
backend/domain/meat_processing/
    exceptions.py   — jerarquía de errores (mirror 1:1 de backend/domain/losses/exceptions.py)
    enums.py        — ProcessType, ProcessingOrderStatus, ProcessingBatchStatus,
                       ExecutionStatus, ConsumptionStatus, WeighingType, OutputType,
                       OutputQualityStatus, YieldStatus
    events.py       — MeatProcessingEvents + build_meat_processing_event()
    entities/
        _validation.py           — required_uuid/optional_uuid/decimal_value (mirror de Losses)
        processing_order.py      — aggregate root, máquina de estados completa (§13, 15 estados)
        processing_batch.py      — aggregate independiente (no lista embebida en la orden)
        process_execution.py     — start/pause/resume/complete/cancel/fail + duración
        material_consumption.py  — draft → pending_posting → posted/reversed
        process_output.py        — un solo tipo discriminado por OutputType (ver nota abajo)
        process_weighing.py      — invariante: manual_override requiere authorized_by_user_id
        yield_reconciliation.py  — variance_pct/unexplained_difference calculados, sin
                                    umbrales hardcodeados
    policies/
        yield_reconciliation_policy.py — clasificación WITHIN_TOLERANCE..CRITICAL,
                                          umbrales siempre provistos por el llamador
        consumption_policy.py          — validación de sobreconsumo vs. tolerancia
        order_closing_policy.py        — ProcessingOrderCloseChecklist + OrderClosingPolicy
```

## Decisión de diseño: `ProcessOutput` unificado

El árbol de archivos del §8 del prompt maestro lista `process_output.py`,
`process_by_product.py` y `process_subproduct.py` como clases separadas. Esta
implementación usa **una sola entidad `ProcessOutput`** discriminada por el enum
`OutputType` (`MAIN_PRODUCT`, `CO_PRODUCT`, `BY_PRODUCT`, `SEMI_FINISHED`,
`WORK_IN_PROGRESS`, `REWORKABLE`, `WASTE`, `LOSS`), porque las tres clases
propuestas comparten exactamente la misma forma de campos (producto, lote,
cantidad, peso, almacén, estado de calidad). Dividir en tres clases idénticas
habría sido duplicación pura sin ninguna diferencia de comportamiento — si
Calidad/Costos exponen en el futuro una regla que sí diferencie por tipo, separar
en ese momento es un cambio barato y retrocompatible.

## Auditoría REGLA CERO / Decimal-only

| Regla | Verificación |
|---|---|
| Toda identidad es UUIDv7 | Todas las entidades validan `id`/`operation_id`/FKs vía `required_uuid`/`optional_uuid` → `backend.shared.ids.validate_uuidv7` en `__post_init__`. Ninguna usa `int`. |
| `entity_id != operation_id` | Verificado explícitamente en las 7 entidades. |
| Sin `AUTOINCREMENT`/`lastrowid`/`MAX(id)+1` | No aplica — sin persistencia en esta fase. |
| Decimal-only | Todo campo de cantidad/peso/tolerancia/porcentaje pasa por `decimal_value()`, que rechaza `float`/`bool` explícitamente con `TypeError`. Cero campos `float` (contraste explícito con el bug legacy de `core/use_cases/produccion.py:42`, ver `PROC-0_legacy_audit.md`). |
| Sin defaults arbitrarios hardcodeados | `ConsumptionPolicy`/`YieldReconciliationPolicy` reciben tolerancias como parámetros del llamador, nunca como constante de módulo. |

## Tests

`tests/unit/meat_processing/test_meat_processing_entities.py` (construcción +
todas las transiciones válidas/inválidas de las 7 entidades),
`test_meat_processing_events.py` (catálogo, envelope, distinción de ids),
`test_meat_processing_policies.py` (clasificación de rendimiento, tolerancia de
consumo, checklist de cierre).

## Pendiente

- `MaterialRequirement`, work centers/recursos, incidencias, reprocesos, empaque,
  etiquetas, genealogía y entidades de sacrificio — fases PROC-7/PROC-11 a
  PROC-13/PROC-17 a PROC-19/PROC-24.
- Persistencia (`backend/infrastructure/db/schema/meat_processing_schema.py`,
  repositorios, `MeatProcessingUnitOfWork`) — PROC-3.
- Use Cases de aplicación que orquesten estas entidades con las políticas
  (`ExecuteProcessingOrder`, `CloseProcessingOrder`, etc.) — PROC-6+.
