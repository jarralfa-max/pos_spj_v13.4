# LOSS-0 — Inventario de legacy de Mermas

Fecha: 2026-08-01. Este inventario refleja el paquete real y no autoriza eliminaciones sin ruta canónica probada y cero consumidores.

## Diagnóstico

El bounded context `Losses` no existe. Conviven dos representaciones funcionales:

1. `mermas` + `WasteApplicationService` + repositorio raíz de waste (ruta usada por la UI).
2. `inventory_waste_event` + `backend/application/inventory/use_cases/register_waste.py` (ruta clasificada de Inventario).

La segunda tiene Decimal, almacén, lote, outbox y auditoría, pero no modela el expediente enterprise. Ninguna equivale a `LossCase`.

## Inventario clasificado

| Elemento | Evidencia | Acción | Destino / condición |
| --- | --- | --- | --- |
| `modulos/merma.py` | Widget de 600+ líneas: dependencias, permisos/PIN, cálculo, auditoría y UI | REWRITE | `frontend/desktop/modules/losses/`; eliminar tras navegación y pruebas |
| `ModuloMerma.MOTIVOS` | Motivos hardcodeados y `Otro` | DELETE | Catálogos configurables de clasificación/causa |
| `UMBRAL_VALOR_ALTO = 500.0` | Policy en UI | MOVE | `LossApprovalPolicy` + settings |
| `_safe_float`, `QDoubleSpinBox`, cálculos | Cantidad, costo y valor usan `float` | REWRITE | Value objects Decimal + inputs estándar |
| `CoreEventBusAdapter` | Publica `WASTE_REGISTERED`, `MERMA_REGISTRADA` y `AJUSTE_INVENTARIO` | DELETE | Outbox post-commit; evento único |
| `MERMA.crear` / `MERMA.autorizar` | Permisos generales verificados en UI | MOVE | Permisos granulares y revalidación backend |
| `DiscountGuard` / PIN | Autorización controlada por diálogo | MOVE | Hot authorization use case |
| `auto_audit` en UI | Auditoría fuera del UoW | MOVE | Audit log transaccional |
| `WasteApplicationService` actual | Coordina fila simple, inventario, finanzas y evento | REWRITE | Casos de uso del bounded context |
| `RegisterWasteUseCase` actual | Un único registro inmediato | REWRITE | Draft, submit, approve, post y reverse |
| `WasteRepository` raíz | Persiste `mermas`; devuelve `operation_id` como `waste_id` | REPLACE | Repositorios LossCase/read model |
| `CanonicalWasteInventoryService` | Puente hacia ledger | WRAP_TEMPORARILY | Puerto `LossInventoryGateway` |
| `inventory/RegisterWasteUseCase` | Segunda mutación y segundo registro | MOVE | Inventario conserva solo el posting físico |
| `inventory_waste_event` | Hecho físico clasificado | REUSE | Referencia de posting desde LossCase |
| `mermas` | Sin workflow, líneas, evidencia, investigación ni disposición | REPLACE | Schema `loss_*` born-clean |
| `ajustes_inventario` | Ajuste genérico paralelo | BLOCKED | Auditar consumidores; pérdidas irán a LossCase |
| `production_yield_analysis` | Expected/real/waste con `REAL` | MOVE | Producción=real; Productos=esperado; Losses=variación |
| `rendimiento_pollo` / derivados | Específico de pollo | REWRITE | Perfil versionado multiespecie |
| menú `MERMA` | Entrada singular con emoji | REWRITE | Entrada `MERMAS` + sidebar canónico |
| `WASTE_MODULE_PHASE11_AUDIT.md` | Describe estado anterior y datos ya obsoletos | REPLACE | Este inventario y plan LOSS-0 |

## Flujos relacionados

- Producción conserva KPI de merma, análisis de rendimiento y outputs waste.
- Inventario distingue merma teórica/real, shrinkage, proceso, caducidad, daño, rechazo, decomiso y disposición.
- Inventario ya distingue coproductos/subproductos aprovechables de waste.
- Finanzas consume `WASTE_REGISTERED`, pero existe también escritura directa mediante adaptador.
- Configuración consolida `total_merma`; navegación carga directamente `ModuloMerma`.

## Bloqueo y allowlist

`ajustes_inventario` queda `BLOCKED`: eliminarlo puede romper conteos/correcciones válidas fuera de Mermas. Responsable: LOSS-6/LOSS-23. Condición: mapa completo de consumidores, reemplazo canónico y paridad probada.

No existe allowlist específica de Losses. Las infracciones son deuda explícita, no excepciones permanentes; el cierre exige allowlist vacía.
