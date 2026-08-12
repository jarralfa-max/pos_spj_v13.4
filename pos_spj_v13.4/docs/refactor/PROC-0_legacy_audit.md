# PROC-0 — Auditoría de legacy: Procesamiento Cárnico / Meat Processing

Estado: **DONE** (auditoría) — el resto del roadmap PROC-1..PROC-26 permanece
`PENDING` salvo lo indicado abajo.

## Alcance

Auditoría previa a la relocalización del bounded context "Procesamiento Cárnico /
Meat Processing / Production Execution / Manufacturing Operations / Future
Slaughter Operations" hacia `backend/{domain,application,infrastructure}` +
`frontend/desktop/modules/meat_processing/`, siguiendo el mismo patrón ya aplicado
a Inventario, Cash Register, CRM y **Mermas/Losses**.

Este documento **no elimina ni modifica ningún archivo legacy**. Solo clasifica.

## Inventario de legacy detectado

| Archivo | Líneas | Clasificación | Nota / condición de eliminación |
|---|---|---|---|
| `modulos/produccion.py` | ~1007 | `WRAP_TEMPORARILY` | UI legacy del tab cárnico. Se mantiene operando sobre la ruta actual hasta que `frontend/desktop/modules/meat_processing/` (PROC-4/PROC-23) exponga las mismas operaciones a través de los nuevos Use Cases (PROC-6..PROC-13). No eliminar antes de tener paridad funcional + tests de regresión. |
| `core/production/production_engine.py` | ~882 | `BLOCKED` | Motor de cálculo de detalle de lote (abrir → agregar salidas → cerrar). Contiene ids tipados `int` (`producto_origen_id`, `receta_id`, `produccion_id`, …) — deuda ya señalada en `docs/refactor/modules/procesamiento_carnico.md`. Condición de eliminación: reemplazado por `ProcessingBatch`/`ProcessExecution`/`ProcessOutput` (PROC-2, este documento) + los Use Cases de ejecución (PROC-8..PROC-10) con cobertura de tests equivalente. |
| `core/use_cases/produccion.py` | ~217 | `BLOCKED` | `GestionarProduccionUC`. **Viola Decimal-only**: `SubproductoInput.peso_kg` está tipado `float` (línea 42) — debe corregirse a `Decimal` como parte de cualquier extracción, no como parche aislado. Publica `PRODUCCION_COMPLETADA` al EventBus legacy; el evento canónico reemplazo es `MeatProcessingEvents.PROCESSING_ORDER_COMPLETED` (PROC-2). Condición de eliminación: cubierto por `ExecuteProcessingOrder`/`CompleteProcessingOrder` (fases futuras). |
| `core/services/production_application_service.py` | ~307 | `BLOCKED` | Fachada de delegación pura hacia `GestionarProduccionUC` + `ProductionEngine` + `RecipeEngine`. Mismos ids `int` señalados en su propio audit doc. Condición de eliminación: sustituida por `backend/application/meat_processing/use_cases/*` (fases futuras). |
| `core/services/finance/production_cost_service.py` | ~260 | `BLOCKED` | Distribución de costo de lotes de producción. Corresponde al límite "Costos administra... costo de transformación" (§6/§46 del prompt maestro) — Procesamiento no debe conocer cuentas contables. Condición de eliminación: Procesamiento emite `PROCESSING_MATERIAL_CONSUMED`/`PROCESSING_OUTPUT_PRODUCED`/`PROCESSING_ORDER_CLOSED` (ya definidos en PROC-2 `events.py`) y el módulo de Costos los consume — ver PROC-22. |
| `backend/application/use_cases/execute_meat_production_use_case.py` | ~113 | `REUSE` (referencia) | Ya vive bajo `backend/application/` con Command/DTO UUID-nativos; es el único fragmento ya alineado con la arquitectura objetivo. Sirve de referencia de "cómo se ve un command ya migrado", pero delega a `ProductionApplicationService` (legacy) — se realineará para delegar a los nuevos Use Cases de `backend/application/meat_processing/` cuando existan (fases futuras). |
| `backend/application/commands/production_commands.py` | ~40 | `MOVE` | Command DTO; candidato a moverse/renombrarse dentro de `backend/application/meat_processing/commands/` una vez existan los Use Cases reales que lo consuman. |
| `backend/application/queries/production_query_service.py` | ~64 | `MOVE` | Read-side query; candidato a `backend/application/meat_processing/queries/` (PROC-5 equivalente). |
| `sync/domain_validators/production_validator.py` | ~119 | `REWRITE` | Validador offline/sync de payloads de producción. Se reescribirá contra los nuevos DTOs UUID/Decimal de `backend/application/meat_processing/` cuando exista soporte offline (PROC-21). |
| `repositories/recetas.py` | — | `BLOCKED` | Remanente legacy de recetas. La fuente de verdad de recetas maestras ya es `backend/domain/products/recipe*.py` (Products bounded context) — correcto según §2/§40 del prompt maestro. Condición de eliminación: cero consumidores de `repositories/recetas.py` fuera de `core/services/recipe_engine.py` y el propio `modulos/produccion.py`. |
| `core/services/recipe_engine.py` | — | `BLOCKED` | `RecipeEngine.ejecutar_produccion` ya fue parcheado para usar `new_uuid()` en vez de `AUTOINCREMENT`/`last_insert_rowid()` (ver `procesamiento_carnico.md`). Sigue siendo motor de *ejecución*, no de definición, de receta — su reemplazo natural es el snapshot de receta que un futuro `ReleaseProcessingOrder` Use Case tomará de Products (§14/§40) más `ProcessExecution`/`MaterialConsumption`/`ProcessOutput` (PROC-2, este documento). |
| `core/services/recipes/recipe_resolver.py`, `recipe_validation_service.py`, `recipe_service.py` | — | `BLOCKED` | Mismos motivos que `recipe_engine.py`. Sin consumidores fuera del árbol `core/services/recipes/` y `modulos/produccion.py` según grep de auditoría; confirmar cero-consumidores formalmente antes de retirar (regla §64 "Cero consumidores"). |

Ningún archivo se clasifica `DELETE` en esta pasada: la relocalización completa
(dominio + aplicación + infraestructura + UI) no existe todavía, así que no hay
ruta nueva que sustituya por completo a la legacy. `DELETE` solo aplica en PROC-25.

## Brechas encontradas (no corregidas en esta pasada)

1. **Referencia colgante**: `docs/refactor/refactor_state.json` y
   `docs/refactor/MODULE_QUEUE.md` marcan `RECETAS` como módulo `DONE` apuntando a
   `docs/refactor/modules/recetas.md`, que **no existe**. No se corrige aquí
   (afecta el tracker global, fuera del alcance de esta auditoría de un solo
   bounded context) — queda documentado para PROC-25.
2. **Catálogo de permisos desactualizado (RESUELTO para Procesamiento en PROC-1)**:
   `core/security/permission_catalog.py` conservaba la entrada plana legacy
   `"PRODUCCION": ["ver", "ejecutar"]` en `CANONICAL_MODULE_PERMISSIONS`. A
   diferencia de Mermas/Losses (que migró a permisos granulares sin registrarse en
   el catálogo), el usuario pidió explícitamente seguir el **estándar de Compras**
   (`backend/application/procurement/permissions.py` / `backend/application/inventory/permissions.py`):
   códigos punteados `MODULO.accion` sí registrados en el catálogo canónico. PROC-1
   amplía `CANONICAL_MODULE_PERMISSIONS["PRODUCCION"]` a la lista granular completa
   — ver `PROC-1_security.md`. La entrada plana `"MERMA": ["ver", "crear", "autorizar"]`
   sigue igual (fuera del alcance de este bounded context).
3. **Violación Decimal-only activa**: `core/use_cases/produccion.py:42`
   (`SubproductoInput.peso_kg: float`).
4. **Ids `int` en firmas activas**: `core/production/production_engine.py` y
   `core/services/production_application_service.py` tipan varios parámetros de
   identidad (`producto_origen_id`, `receta_id`, `produccion_id`) como `int` en vez
   de `str`/UUID. Ya señalado en `procesamiento_carnico.md` como "no son casts, no
   rompen runtime" — sigue siendo deuda real si se relocaliza sin corregir.

## Roadmap PROC-0..PROC-26

| Fase | Descripción | Estado |
|---|---|---|
| PROC-0 | Auditoría de legacy | **DONE** (este documento) |
| PROC-1 | Seguridad (permisos, alcance, segregación, autorización, auditoría) | **DONE** (ver `PROC-1_security.md`) |
| PROC-2 | Dominio base (ProcessingOrder, ProcessingBatch, Execution, Consumption, Output, Weighing, YieldReconciliation, Policies, Events) | **DONE** (ver `PROC-2_domain.md`) |
| PROC-3 | Esquema limpio (UUIDv7, Decimal, constraints, outbox, bootstrap) | **DONE** (ver `PROC-3_schema.md`) |
| PROC-4 | Sidebar y navegación | **DONE** (ver `PROC-4_navigation.md`) |
| PROC-5 | Planeación (ProductionPlan) | **DONE** (ver `PROC-5_planning.md`) |
| PROC-6 | Órdenes (creación, aprobación, snapshot, liberación) | PENDING |
| PROC-7 | Preparación (requerimientos, reservas, lotes, recursos, operarios) | PENDING |
| PROC-8 | Ejecución (inicio, pausa, reanudación, steps, incidencias) | PENDING |
| PROC-9 | Consumos y pesajes (báscula, override manual, inventario) | PENDING |
| PROC-10 | Outputs (principal, coproductos, subproductos, WIP, inventario) | PENDING |
| PROC-11 | Despiece (esquemas, multiespecie, huesos, grasa, recortes) | PENDING |
| PROC-12 | Derivados (molido, mezclado, marinado, formulación, multinivel) | PENDING |
| PROC-13 | Empaque (empaque, reempaque, lotes, caducidad, etiquetas) | PENDING |
| PROC-14 | Rendimientos (esperado, real, tolerancias, conciliación, alertas) | PENDING |
| PROC-15 | Mermas (variación, LossCase, idempotencia, integración) | PENDING |
| PROC-16 | Calidad (solicitudes, bloqueos, liberaciones, reproceso) | PENDING |
| PROC-17 | Reprocesos (ReworkOrder, reservas, ejecución, inspección) | PENDING |
| PROC-18 | Trazabilidad (genealogía, lotes, upstream/downstream, recall) | PENDING |
| PROC-19 | Recursos y capacidad (áreas, centros, estaciones, equipos) | PENDING |
| PROC-20 | Notificaciones y WhatsApp | PENDING |
| PROC-21 | Offline (outbox, secuencia, sync, conflictos) | PENDING |
| PROC-22 | Costos y Finanzas (eventos, consumos, outputs, variaciones) | PENDING |
| PROC-23 | UI/UX (sidebar, páginas, ejecución, tema JUANIS) | PENDING |
| PROC-24 | Preparación de sacrificio (entidades, contracts, feature flags) | PENDING |
| PROC-25 | Eliminación de legacy | PENDING |
| PROC-26 | Validación final | PENDING |
