# LOSS-0 — Consolidación de schema de Mermas

| Tabla/modelo | Estado | Problema | Objetivo |
| --- | --- | --- | --- |
| `mermas` | REPLACE | Registro plano, `REAL`, motivo libre, sin workflow/evidencia/almacén/lote | Agregado `loss_*` |
| `inventory_waste_event` | REUSE | Hecho de Inventario, no expediente | Posting físico vinculado a LossCase |
| `ajustes_inventario` | MERGE | Puede ocultar pérdidas | Pérdidas a LossCase; otros ajustes al ledger |
| `production_yield_analysis` | MERGE | Mezcla análisis y expediente | Producción conserva real; Losses la variación |
| `rendimiento_pollo` / derivados | REPLACE | Específico y `REAL` | Perfiles versionados multiespecie |
| recetas/componentes | REUSE | Fuente candidata de esperado | Ownership de Productos; Losses referencia versión |

## Incompatibilidades verificadas

- El schema base crea `mermas` y `ajustes_inventario`; Inventario crea además `inventory_waste_event`.
- La UI escribe la primera tabla y la ruta clasificada de Inventario escribe la segunda.
- `WasteRepository.register_waste()` genera UUIDv7, pero devuelve `operation_id`, confundiendo entidad e idempotencia.
- Cantidad, costo, valor y porcentajes usan `REAL`; el objetivo exige Decimal sin pérdida.
- Motivo/tipo no están respaldados por catálogos configurables y versionados.
- Faltan constraints de workflow, aprobación, recuperación, disposición y segregación.

## Modelo objetivo mínimo para LOSS-3

- `loss_cases`, `loss_lines`, `loss_classifications`, `loss_reasons`.
- `loss_evidence`, `loss_approvals`, `loss_dispositions`, `loss_recoveries`.
- `yield_variances`, `loss_investigations`, `root_causes`.
- `corrective_actions`, `corrective_action_tasks`.
- `loss_audit_log`, `loss_outbox`, `loss_processed_operations`.

Todos los IDs/FK serán UUIDv7 `TEXT`; los valores decimales tendrán representación canónica. `operation_id`, `event_id` y `entity_id` serán distintos.

## Ownership y estrategia

Losses posee expediente/workflow; Inventario movimiento/balance; Productos rendimiento esperado; Producción rendimiento real; Calidad conformidad; Costos impacto; Finanzas contabilización post-commit.

No habrá rescate, lectura dual ni escritura dual. LOSS-3 corregirá schema fuente/bootstrap y la DB local se reconstruirá solo cuando implementación y pruebas estén listas. LOSS-0 no elimina datos.
