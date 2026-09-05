# PROC-6 — Órdenes: Procesamiento Cárnico

Estado: **DONE** (Use Cases de creación, aprobación, snapshot de receta y
liberación; sin preparación de materiales/ejecución todavía — eso es PROC-7/8)

## Alcance

Primera capa de aplicación real del bounded context: `CreateProcessingOrderUseCase`,
`ApproveProcessingOrderUseCase`, `ReleaseProcessingOrderUseCase` — el ciclo
"Creación → Aprobación → Snapshot → Liberación" que PROC-6 nombra
explícitamente, construido sobre el dominio (PROC-2/PROC-5) y la persistencia
(PROC-3) ya existentes, siguiendo el patrón de casos de uso más maduro del
repo (`backend/application/inventory/use_cases/adjustment_use_cases.py`).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/application/meat_processing/result.py` | `MeatProcessingResult` (`ok`/`fail`, mirror de `InventoryResult`) — todo Use Case devuelve esto, nunca lanza al llamador. |
| `backend/application/meat_processing/ports.py` | `RecipeSnapshot` (payload congelado: versión de receta/despiece/rendimiento + componentes, outputs, unidades, factores, tolerancias, parámetros técnicos, empaque, calidad — §14) + `RecipeSnapshotPort` (Protocol) + `NullRecipeSnapshotPort` (default: sin integración con Productos todavía, resuelve `None`). |
| `backend/application/meat_processing/use_cases/processing_order_use_cases.py` | `CreateProcessingOrderUseCase`, `ApproveProcessingOrderUseCase`, `ReleaseProcessingOrderUseCase` — cada uno: `self._auth.require(...)` primero, alcance sucursal/almacén vía `MeatProcessingExecutionContext`, idempotencia, mutación de dominio, `uow.orders.save()`, evento en `uow.outbox`, registro en `uow.audit`. |

## Creación

`CreateProcessingOrderUseCase` construye una `ProcessingOrder` nueva (`DRAFT`)
y, salvo que el llamador pase `submit_for_approval=False`, la envía de
inmediato a `PENDING_APPROVAL` (mismo patrón que `RegisterGeneralLossCommand.submit`
en Losses). Idempotente por `operation_id`: un reintento con el mismo
`operation_id` devuelve la orden ya creada (`already_processed=True`) en vez
de fallar por `operation_id` duplicado (constraint `UNIQUE` de PROC-3).

## Aprobación

`ApproveProcessingOrderUseCase` mueve `PENDING_APPROVAL → APPROVED`.
La segregación de funciones (aprobador ≠ creador) **no se revalida aquí** —
ya la exige `ProcessingOrder.approve()` en el dominio (PROC-2), que ahora
lanza `MeatProcessingSegregationOfDutiesError` (ver corrección abajo).
Idempotente por estado: reintentar sobre una orden ya `APPROVED` devuelve
éxito idempotente en vez de error de transición.

## Snapshot (§14)

`ReleaseProcessingOrderUseCase` resuelve el snapshot **antes** de liberar,
solo si la orden todavía no tiene ninguno de los tres ids de versión
(`recipe_version_id`/`cutting_scheme_version_id`/`yield_profile_version_id`)
capturados — así un reintento nunca vuelve a llamar `RecipeSnapshotPort` ni
intenta recapturar (`ProcessingOrder.apply_recipe_snapshot()`, nuevo en
PROC-2, rechaza una segunda captura con `MeatProcessingInvariantError`: el
snapshot es inmutable). El payload completo se audita en
`meat_processing_audit_log` (`action="RECIPE_SNAPSHOT_CAPTURED"`,
`after_json`) — no se creó una tabla nueva para esto; se reutiliza la
infraestructura de auditoría que PROC-3 ya construyó.

`RecipeSnapshotPort` es el contrato que una futura integración real con
Productos implementará (§40: `ActiveRecipeQueryService`,
`RecipeVersionSnapshotQueryService`, `ActiveYieldProfileQueryService`,
`ActiveCuttingSchemeQueryService`); `NullRecipeSnapshotPort` deja el Use Case
funcional hoy sin esa integración (una orden de un proceso sin receta, p. ej.
`PACKAGING`, libera igual con los tres ids en `None`).

## Liberación

`ReleaseProcessingOrderUseCase` termina llamando `ProcessingOrder.release()`
(`APPROVED`/`READY` → `RELEASED`). Idempotente por estado igual que
aprobación.

## Corrección de dominio: tipo de excepción de segregación de funciones

Al construir el mapeador de errores (`_fail()`) se detectó que
`ProcessingOrder.approve()`/`.reverse()` y `ProductionPlan.approve()` (PROC-2/
PROC-5) lanzaban `MeatProcessingInvariantError` genérico para la regla de
segregación de funciones, en vez del `MeatProcessingSegregationOfDutiesError`
ya definido para ese propósito exacto desde PROC-1. Se corrigió en las tres
ubicaciones — ahora `_fail()` puede distinguir `SEGREGATION_OF_DUTIES` de
`MEAT_PROCESSING_RULE_VIOLATION` genérico, algo que un llamador (UI) sí
necesita diferenciar. Tests de PROC-2/PROC-5 actualizados en consecuencia.

## Auditoría REGLA CERO

| Regla | Verificación |
|---|---|
| Toda mutación revalida permiso | `test_every_use_case_class_calls_authorization_require` (arquitectura): cada clase de Use Case llama `self._auth.require(...)`. |
| Sin SQL crudo en Use Cases | `test_use_cases_never_execute_raw_sql` — todo pasa por `MeatProcessingUnitOfWork`. |
| Idempotencia estructural | `operation_id` único (creación) + chequeo de estado ya alcanzado (aprobación/liberación) — sin duplicar eventos ni reintentar el snapshot. |
| Auditoría de excepciones | `AuthorizationGrant`/`meat_processing_authorization_log` quedan listos desde PROC-1/PROC-3 para cuando una autorización en caliente real se necesite (p. ej. liberar con material pendiente) — no se usó todavía porque ningún flujo de PROC-6 lo requiere aún. |

## Tests

`tests/integration/meat_processing/test_meat_processing_processing_order_use_cases.py`
(creación con/sin envío a aprobación, idempotencia, permiso denegado, alcance
de sucursal denegado, auditoría+outbox registrados; aprobación feliz,
idempotente, auto-aprobación rechazada, orden inexistente; liberación sin
snapshot, con snapshot capturado y auditado, idempotente sin recapturar,
orden inexistente, liberación antes de aprobar rechazada; ciclo de vida
completo creación→aprobación→liberación con tres actores distintos),
`tests/architecture/test_meat_processing_use_cases_are_authorized.py`.
Además, `tests/unit/meat_processing/test_meat_processing_entities.py` ganó
3 tests para `ProcessingOrder.apply_recipe_snapshot()`.

## Pendiente

- `SubmitProcessingOrderForApprovalUseCase` independiente si algún flujo futuro
  necesita crear en `DRAFT` y enviar a revisión en un paso separado (hoy
  `submit_for_approval` es un flag de creación).
- Preparación (§15: requerimientos, reservas, disponibilidad, capacidad) antes
  de que una orden pueda pasar a `READY` — PROC-7.
- `MeatProcessingUseCaseFactory` (composition root, patrón
  `InventoryUseCaseFactory`) — se construye cuando exista un punto de
  integración real (UI o API) que la necesite; hasta entonces, los Use Cases
  se instancian directamente con su default `permissive_for_tests()`.
- Integración real de `RecipeSnapshotPort` contra Productos — cuando ese
  bounded context exponga las query services de §40.
