# PROC-26 — Validación final: Procesamiento Cárnico

## Estado

`BACKEND MIGRADO / UI PARCIAL / LEGACY VIGENTE` — deliberadamente no
`MIGRATED`: a diferencia de Transferencias o Mermas al cerrar su fase
final, Procesamiento Cárnico **no** ha cortado su ruta legacy (ver
`PROC-25_legacy_removal_readiness.md`). Lo que sí está migrado, probado y
cerrado es el backend completo (dominio + aplicación + infraestructura) y
la primera página de UI real. Este documento valida honestamente ese
alcance — no infla el estado del 18/19 de UI que sigue pendiente.

## Alcance de la validación

Cubre el trabajo de PROC-1 a PROC-25 sobre
`backend/{domain,application,infrastructure}/meat_processing/`,
`frontend/desktop/modules/meat_processing/`,
`backend/infrastructure/desktop/meat_processing_factory.py`,
`sync/domain_validators/meat_processing_validator.py`, y las migraciones
187/248-252. No revalida los demás bounded contexts del ERP (Losses,
Inventory, etc.) más allá de confirmar que nada de este trabajo los
regresionó.

## Matriz ejecutable

| Validación | Evidencia automatizada | Resultado |
|---|---|---|
| Dominio | `tests/unit/meat_processing/` (187 tests: 22 entidades, políticas, catálogos de eventos/enums, contratos de sacrificio) | ✅ |
| Aplicación (casos de uso) | `tests/integration/meat_processing/` (172 tests sobre 48 clases `*UseCase`) | ✅ |
| Arquitectura (permisos granulares, autorización en cada Use Case, UoW-only, sin SQL en presenters) | `tests/architecture/test_meat_processing_*.py` (13 tests) | ✅ |
| UUIDv7 / Decimal-only | `entities/_validation.py` (`required_uuid`/`decimal_value`, rechazo explícito de `float`) + tests dedicados por entidad | ✅ |
| Esquema / bootstrap limpio | 6 migraciones (187, 248, 249, 250, 251, 252), `CREATE TABLE IF NOT EXISTS`, `CHECK` en cada columna decimal, `UNIQUE(operation_id)` en cada tabla transaccional | ✅ |
| Idempotencia | `operation_id` UNIQUE por entidad + `meat_processing_processed_events` para operaciones compuestas (PROC-11/15/17/20) | ✅ |
| Segregación de funciones | `ProcessingOrder.approve()`, `ReworkOrder.approve()`, `ProductionPlan.approve()`, `ProcessingOrder.reverse()` — verificado por tests dedicados y por el presenter e2e (PROC-23) | ✅ |
| Eventos y permisos | `MeatProcessingEvents` (36 eventos canónicos) / `MeatProcessingPermissions` (94 permisos), registrados en `core/security/permission_catalog.py`, `tests/unit/test_permission_matrix_catalog_first.py` | ✅ |
| Integraciones cross-context | Port+Null en los 6 límites de bounded context: `RecipeSnapshotPort` (Products), `InventoryConsumptionPort`/`InventoryReceiptPort` (Inventory), `LossCaseRequestPort` (Losses), `QualityInspectionPort` (Calidad), `NotificationPort` (WhatsApp/notificaciones), `CostAllocationPort` (Costos) — ninguno finge éxito sin confirmación real | ✅ (contratos listos, integraciones reales pendientes — ver Pendiente) |
| Offline / sync | `sync/domain_validators/meat_processing_validator.py` (10 tests) + registro en `TABLAS_SINCRONIZABLES`/`SERVER_AUTH_TABLES` (PROC-21) | ✅ |
| UI | `ProcessingOrdersPage` + `ProcessingOrderPresenter` + `MeatProcessingModuleHost` — 17 tests (`tests/integration/meat_processing/test_meat_processing_ui_presenter.py`, `test_meat_processing_view_shell.py`) | ✅ (1 de 19 secciones; ver Pendiente) |
| Legacy | `modulos/produccion.py` + motor legacy completo siguen vivos e instanciados por `core/app_container.py`; cero archivos reclasificados a `DELETE` | ⚠️ **por diseño** — ver `PROC-25_legacy_removal_readiness.md` |
| Regresión en módulos hermanos | `tests/unit/test_permission_matrix_catalog_first.py`, `tests/unit/losses/`, `tests/test_refactor_v133.py`, `tests/integration/test_meat_production_use_case.py`, `tests/integration/test_phase0_phase1_scaffolding.py` | ✅ (133/133) |

## Números del pipeline (PROC-1..PROC-25)

- **48** casos de uso (`backend/application/meat_processing/use_cases/`).
- **22** entidades de dominio (`backend/domain/meat_processing/entities/`), más 7 contratos de sacrificio (stub, PROC-24).
- **6** migraciones (`187`, `248`-`252`), todas `CREATE TABLE IF NOT EXISTS` aditivas.
- **94** permisos granulares, **36** eventos de dominio canónicos.
- **372** tests bajo `tests/unit/meat_processing/` + `tests/integration/meat_processing/` + `tests/architecture/test_meat_processing_*.py` — **372/372 en verde**.
- **1** página de UI funcional real (Órdenes) de 19 secciones de navegación.
- **6** puertos Port+Null para integración cross-context, ninguno conectado a una implementación real todavía.

## Resultado

- Identidades: `TEXT` UUIDv7 vía `backend.shared.ids.new_uuid()`/`validate_uuidv7`; sin `AUTOINCREMENT` ni `lastrowid` en ninguna tabla nueva.
- Cantidades/pesos/porcentajes: `Decimal` en dominio, `TEXT` decimal en esquema con `CHECK (CAST(x AS NUMERIC) ...)`; `float` rechazado explícitamente en validadores de entidad y en el nuevo validador de sync.
- Cada caso de uso re-valida su propio permiso (`self._auth.require(...)`) — verificado estructuralmente por `test_meat_processing_use_cases_are_authorized.py`, no solo por convención.
- El presenter de UI (`ProcessingOrderPresenter`) nunca ejecuta SQL ni importa repositorios — solo llama `use_case.execute(...)`, verificado por guardrail de arquitectura (corregido en PROC-23 tras encontrar un falso positivo pre-existente, también presente en Losses).
- El bounded context completo puede sincronizarse offline: 20 tablas registradas, 8 clasificadas `SERVER_AUTH` (agregados transaccionales), el resto en LWW por defecto.
- **La ruta legacy permanece 100% intacta y en uso activo** — esto es correcto para el estado actual del proyecto, no un defecto de esta fase: cortarla hoy eliminaría funcionalidad operativa real (Regla 0).

## Pendiente (honesto, no heredado ciegamente de fases anteriores)

1. **UI**: 18 de 19 secciones de `MEAT_PROCESSING_NAV` siguen en placeholder. Es el bloqueador real para poder ejecutar PROC-25 de verdad (ver su checklist).
2. **Integraciones reales** detrás de los 6 puertos Port+Null — ninguna tiene todavía un adaptador real conectado (Products/Inventory/Losses/Calidad/Notificaciones/Costos). Los use cases que dependen de ellas hoy responden honestamente `*_INTEGRATION_PENDING` en vez de fingir éxito.
3. **Recursos (PROC-19)**: sin FK real entre `processing_orders.work_center_id`/`.production_area_id` y el catálogo nuevo — referencia de aplicación, no de base de datos (limitación de SQLite documentada en su momento).
4. **Sacrificio (PROC-24)**: `SLAUGHTER_ENABLED = False` — contratos y enums existen, sin motor de ejecución; correcto mientras el negocio no active esa línea.
5. **Legacy**: ver checklist completo de 5 pasos en `PROC-25_legacy_removal_readiness.md` — nada de esto se resuelve solo, requiere las 18 páginas de UI primero.

Ninguno de estos puntos bloquea el uso del backend nuevo por integraciones
futuras (WhatsApp, API externa, otra UI) — el motivo de que sigan
pendientes es exclusivamente la superficie de UI que aún falta construir,
no una limitación del dominio/aplicación, que están completos y probados.
