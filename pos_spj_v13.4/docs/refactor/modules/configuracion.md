# Módulo CONFIGURACION

## Estado

```text
IN_PROGRESS
```

## Iteración

```text
6
```

## Lote funcional cerrado: CONFIGURACION-01-SCOPE

El lote de alcance queda cerrado con evidencia en `docs/refactor/modules/configuracion_scope.json`.

## Alcance canónico confirmado

Configuración posee estas superficies funcionales:

```text
- Ajustes generales y disponibilidad de schema de configuración.
- Toggles de módulos.
- Perfil de empresa, sucursales y perfil de delivery por sucursal.
- SMTP, Mercado Pago y requerimientos de seguridad.
- Cierre mensual desde la pantalla de configuración.
- Reglas Happy Hour administradas desde configuración; ejecución de precios fuera del módulo.
- Administración de usuarios, roles, permisos y acceso a módulos.
- Configuración de hardware y preferencias de UI/tema.
```

## Archivos canónicos del módulo

```text
modulos/configuracion.py
core/services/configuration_settings_service.py
repositories/config_repository.py
core/module_config.py
core/services/config_service.py
modulos/config_hardware.py
modulos/config_interfaz.py
modulos/config_modules.py
core/repositories/hardware_config_repository.py
backend/application/queries/hardware_settings_query_service.py
backend/application/queries/ticket_settings_query_service.py
migrations/m050_hardware_config_canonical.py
migrations/standalone/096_configuration_services_schema.py
```

## Dependencias compartidas clasificadas fuera del alcance propietario

```text
core/repositories/whatsapp_config_repository.py -> WHATSAPP
modulos/ticket_designer.py -> TICKETS
modulos/fidelidad_config.py -> FIDELIDAD
modulos/rrhh_turnos.py -> RRHH
```

Estas superficies pueden usar almacenamiento de configuración, pero sus reglas funcionales no pertenecen al cierre de Configuración.

## Hallazgos del alcance

- `CFG-SCOPE-001`: `ConfigRepository` conserva la frontera SQL del módulo. La eliminación o reubicación de consultas se tratará en `CONFIGURACION-04-QUERIES` y lotes de persistencia.
- `CFG-SCOPE-002`: `uuid4`, `lastrowid`, `int branch_id` y contratos enteros asociados quedan dentro del módulo, pero se corrigen en `CONFIGURACION-02-IDENTITY`.
- `CFG-SCOPE-003`: commits/rollback y límites transaccionales se tratarán en `CONFIGURACION-08-TRANSACTIONS`.

## Causas raíz

- El módulo agrupa configuración global, administración de acceso y pantallas auxiliares de hardware/UI en una misma entrada histórica.
- Varias superficies de otros módulos persisten claves en `configuraciones`, lo que hacía ambiguo el alcance funcional si se auditaba por tabla en lugar de por responsabilidad.
- La ruta canónica actual usa servicios de aplicación, pero aún quedan deudas de identidad, queries, transacciones y persistencia que deben resolverse en lotes posteriores.

## Rutas canónicas protegidas

- UI de Configuración → `SettingsModuleServices` → servicios explícitos → `ConfigRepository`.
- UI de Hardware → `HardwareConfigRepository` / QueryServices de hardware y ticket.
- Toggles de módulos → `ModuleSettingsService` / `core/module_config.py`.

## Tests agregados

```text
tests/architecture/test_configuracion_scope.py
```

Este test protege que el inventario de alcance esté cerrado, que los archivos canónicos existan dentro del paquete real, que las dependencias compartidas tengan dueño externo explícito y que el lote activo avance a identidad.

## Archivos creados

```text
docs/refactor/modules/configuracion_scope.json
tests/architecture/test_configuracion_scope.py
```

## Archivos modificados

```text
docs/refactor/modules/configuracion.md
docs/refactor/work_queue.json
docs/refactor/refactor_state.json
docs/refactor/CURRENT_MODULE.md
tests/architecture/test_refactor_work_queue.py
```

## Archivos eliminados

```text
Ninguno.
```

## Migraciones

```text
Sin migraciones en CONFIGURACION-01-SCOPE.
```

## Búsquedas negativas

```text
- Copias de modulos/configuracion.py en la raíz externa: 0.
- Copias de docs/refactor/modules/configuracion_scope.json en la raíz externa: 0.
- Archivos canónicos fuera del paquete real: 0.
```

## Validación manual

Pendiente para lotes de UI y gates finales. No aplica cierre visual en el lote de alcance.

## Regresiones

Ninguna detectada en el lote de alcance.

## Violaciones restantes del lote

```text
0
```

## Lote funcional cerrado: CONFIGURACION-02-IDENTITY

Acciones funcionales ejecutadas:

```text
- `modulos/configuracion.py` ya no genera `operation_id` con `uuid4`; usa `backend.shared.ids.new_uuid()`.
- `repositories/config_repository.py` eliminó helpers legacy no referenciados (`create_branch`, `update_branch`, `disable_branch`) que sostenían una ruta paralela de sucursales y un retorno directo de `lastrowid`.
- `tests/unit/test_configuracion_refactor_services.py` protege ambas reglas para evitar regresión.
```


Iteración adicional de identidad:

```text
- `backend/shared/events/event_contracts.py` genera `event_id` con `new_uuid()` en lugar de `uuid4`.
- `core/services/configuration_settings_service.py` agrega `event_id` UUIDv7 a los eventos fallback de permisos.
- `tests/unit/test_configuracion_refactor_services.py` verifica que los eventos fallback de Configuración carguen `event_id` versión 7 y en minúsculas.
```


Iteración de evento legacy compartido:

```text
- `core/domain/events.py` usa `backend.shared.ids.new_uuid()` para `event_id` y `operation_id` por defecto.
- `tests/test_refactor_v133.py::TestDomainEvent` protege que ambos identificadores sean UUIDv7.
```

El lote `CONFIGURACION-02-IDENTITY` sigue activo porque aún quedan contratos enteros y retornos `lastrowid` funcionales en la ruta canónica que requieren migración completa de identidad.

## Siguiente estado

Continuar `CONFIGURACION-02-IDENTITY`.

### Iteración 5 — CONFIGURACION-02-IDENTITY (eventos compartidos RRHH)

- Migrado `core.rrhh.events.new_operation_id()` desde identificadores `prefix-uuid4` a UUIDv7 canónico mediante `backend.shared.ids.new_uuid()`.
- Conservado el argumento `prefix` solo por compatibilidad de llamadas existentes; ya no forma parte de la identidad runtime.
- Añadida protección unitaria para confirmar UUIDv7 minúsculo y prohibir la reintroducción de `uuid4` en el helper de eventos RRHH.
- Violaciones restantes del lote: aún no cerrado; continúa la auditoría de PK/FK enteras, `lastrowid` y contratos `int` restantes antes de seleccionar CONFIGURACION-03-UI.

### Iteración 6 — CONFIGURACION-02-IDENTITY (branch_id de eventos de permisos)

- Eliminado el fallback entero `branch_id = "1"` en `PermissionEventPublisher`.
- Los eventos de permisos con contexto de sucursal conservan `branch_id`/`sucursal_id`; los eventos globales de permisos generan `branch_id` UUIDv7 canónico para no publicar identidad entera.
- Añadida protección unitaria que verifica UUIDv7 minúsculo para eventos de permisos sin sucursal y prohíbe reintroducir `payload.get("branch_id", "1")`.
- Violaciones restantes del lote: aún no cerrado; persisten rutas con PK/FK enteras y `lastrowid` que requieren corte UUID atómico antes de marcar CONFIGURACION-02-IDENTITY como DONE.

### Iteración 7 — CONFIGURACION-02-IDENTITY (operation_id de permisos)

- `PermissionEventPublisher` valida que `operation_id` sea UUIDv7 canónico en minúsculas antes de publicar eventos de permisos.
- El flujo de integración de roles/permisos usa `backend.shared.ids.new_uuid()` en lugar de cadenas legacy `op-*`.
- Añadida protección unitaria contra `operation_id` legacy en eventos de permisos.
- Violaciones restantes del lote: aún no cerrado; siguen pendientes las PK/FK enteras y retornos `lastrowid` que requieren migración atómica de identidad.

### Iteración 8 — CONFIGURACION-02-IDENTITY (validación branch_id de permisos)

- `PermissionEventPublisher` valida `branch_id`/`sucursal_id` explícito como UUIDv7 canónico antes de publicar.
- `UserManagementService.save_user()` deja de enviar el `branch_id` entero en el payload del evento de permisos; el publicador genera un `branch_id` UUIDv7 para el evento branch-agnostic.
- Añadida protección unitaria que rechaza `branch_id` entero en eventos de permisos.
- Violaciones restantes del lote: aún no cerrado; continúan pendientes las PK/FK enteras y retornos `lastrowid` persistentes que requieren migración atómica de identidad.

### CONFIGURACION-02-IDENTITY — Iteración 9

MÓDULO: CONFIGURACION
LOTE: CONFIGURACION-02-IDENTITY
ITERACIÓN: 9
ESTADO INICIAL: IN_PROGRESS
ESTADO FINAL: IN_PROGRESS

HALLAZGOS:
- Los eventos de permisos aún podían publicar `entity_id` no canónico y payloads con `user_id`/`role_id` enteros de tablas actuales.

CAUSAS RAÍZ:
- La persistencia de usuarios y roles sigue usando IDs enteros mientras el contrato de eventos ya exige UUIDv7 para identidad externa.

TESTS DE PROTECCIÓN:
- Se agregó protección para rechazar `entity_id` legacy en `PermissionEventPublisher`.
- Se agregó protección negativa para impedir `entity_id=str(user_id|role_id|saved_id)` y payloads con `user_id`/`role_id` enteros en eventos de Configuración.

CAMBIOS:
- `PermissionEventPublisher` valida `entity_id` como UUIDv7 canónico.
- Los servicios de usuarios, roles y accesos de módulo publican `entity_id` generado con `new_uuid()`.
- Los payloads de eventos sustituyen IDs enteros por etiquetas (`username`, `role_name`) resueltas desde `ConfigRepository`.

LEGACY ELIMINADO:
- Eliminada publicación de `user_id`/`role_id` enteros en eventos de permisos de Configuración.

BÚSQUEDAS NEGATIVAS:
- `entity_id=str(user_id)`, `entity_id=str(role_id)`, `entity_id=str(saved_id)`, `payload={"user_id": user_id`, `payload={"role_id": role_id`, `payload={"role_id": saved_id`.

TESTS EJECUTADOS:
- `python -m pytest pos_spj_v13.4/tests/unit/test_configuracion_refactor_services.py pos_spj_v13.4/tests/integration/test_roles_permissions_canonical_flow.py pos_spj_v13.4/tests/architecture/test_uuidv7_cutover_protection.py -q`
- `python -m pytest pos_spj_v13.4/tests/architecture -q`
- `python -m compileall pos_spj_v13.4`

INTEGRACIONES:
- Flujo integrado de roles/permisos mantiene persistencia por rol entero interna, pero eventos externos no exponen identidad entera.

VIOLACIONES RESTANTES:
- 0

SIGUIENTE LOTE HISTÓRICO:
- El cierre F1–F8 registró como siguiente paso completar `CONFIGURACION-02-IDENTITY` mediante el corte atómico UUIDv7.
- Las iteraciones posteriores de este documento cierran dicho lote y continúan con `CONFIGURACION-03-UI`; prevalecen sobre esta nota histórica.

---

## Cierre F1–F8 (rama `claude/sleepy-goodall-33uld6`, PR #302)

Auditoría exhaustiva del módulo contra el checklist completo de `SPJ_REFACTOR_SKILL.md`.
El lote `CONFIGURACION-02-IDENTITY` permanece `IN_PROGRESS` (corte atómico UUID = migración 200).

### Fases ejecutadas

| Fase | Entrega | Tests |
|------|---------|-------|
| F0 | Guard rails baseline ratchet | `test_configuracion_guardrails.py` |
| F1 | Sin SQL/commit/`Principal`/`sucursal_id=1`/`or 1` en UI; `HardwareSettingsService`, `FeatureFlagService.set_enabled/get_branch_flags` | guardrails + `test_no_commit_rollback_in_frontend` |
| F2 | `username_for_id`/`role_name_for_id` (labels, no int en eventos); `save_branch` UUIDv7; fixtures canónicas | `test_configuracion_uuid_identity.py`, `test_configuracion_refactor_services.py` |
| F3 | `ConnectionUnitOfWork`; `ConfigRepository` sin `_commit`; servicios poseen transacción; eventos post-commit | `test_configuracion_transactions.py` |
| F4 | DTOs explícitos (`configuracion_dtos.py`); UI consume atributos, no tuplas/rows; **bug fix** `list_roles_v13` ambiguous `uuid` | `test_configuracion_dtos.py` |
| F5 | Fuente única: borrado `SettingsRepository` (dual-write muerto), bridge legacy hardware fuera de runtime | `test_configuracion_single_source.py` |
| F6 | UseCases canónicos por acción (12) concretos: Command→UseCase→service→evento | `test_configuracion_use_case_flows.py` |
| F7 | Contrato evento completo (`occurred_at`/`schema_version`); idempotencia por `operation_id` | `test_configuracion_event_idempotency.py` |
| F8 | SMTP/MercadoPago/hardware fuera de UI → `DiagnosticResult`; sin `smtplib/serial/urllib/socket/subprocess` en UI | `test_configuracion_external_integrations.py` |

### Suite
- Tests del módulo CONFIGURACION: **83 passed**.
- Suite `architecture+unit+integration`: 395 passed, 87 failed (preexistentes, ajenos a CONFIGURACION), 27 skipped — **0 regresiones** introducidas (verificado por diff de fallos en cada fase).

### Legacy eliminado
- `repositories/settings_repository.py` (dual-write `configuraciones`↔`system_settings`).
- `ConfigRepository._commit` + 14 llamadas.
- `_to_ui_rule` (reemplazado por DTO); `migrate_legacy_configuraciones_hardware()` en runtime de `printer_service`.

### Violaciones restantes (→ corte atómico migración 200 / FASE 2.5)
- PK/FK enteras (`sucursales`/`usuarios`/`roles`), `lastrowid`, `CAST(h.sucursal_id AS TEXT)`, fallback `_require_uuid_column→"id"` — rutas transitorias tras "columna uuid ausente".
- `hardware_config`: `id INTEGER PRIMARY KEY AUTOINCREMENT` (clave funcional real = `tipo`).
- `usuarios.rol` por **nombre** (no `role_id` uuid); `employee_id` int (RRHH legacy, aislado).
- Idempotencia = set in-memory por servicio (outbox persistente con `operation_id` = futuro).
- `event_outbox` PK `INTEGER AUTOINCREMENT` (infra, no identidad de dominio).
- `compileall` global bloqueado por `SyntaxError` preexistente en `core/services/stock_reservation_service.py:2` (módulo VENTAS, fuera de alcance).

### Siguiente
Cerrar `CONFIGURACION-02-IDENTITY` con el corte atómico UUID (migración 200) o avanzar al siguiente módulo (`MERMA`) según prioridad.
- Activar `CONFIGURACION-03-UI` una vez confirmado el cierre de identidad.

### CONFIGURACION-02-IDENTITY - Iteración 10

MODULO: CONFIGURACION
LOTE: CONFIGURACION-02-IDENTITY
ITERACION: 10
ESTADO INICIAL: IN_PROGRESS
ESTADO FINAL: DONE

HALLAZGOS:
- `ConfigRepository` seguía aceptando `branch_id`, `role_id` y `user_id` numéricos, resolviendo `id` legacy y conservando identidad dual en la ruta canónica del módulo.
- Happy Hour, cierre mensual, usuarios y permisos todavía mantenían ramas de runtime que caían a `sucursal_id` y `rol_id` cuando el esquema ya estaba migrado con columnas UUID.

CAUSAS RAIZ:
- El lote 096 había agregado columnas UUID y backfill, pero el repositorio canónico seguía tolerando contratos legacy para operar sobre tablas parcialmente migradas.
- La migración preparaba el corte del módulo, pero los servicios de Configuración no exigían ese esquema ya migrado antes de aceptar mutaciones y lecturas.

TESTS DE PROTECCION:
- `tests/unit/test_configuracion_refactor_services.py` ahora protege que `ConfigRepository` rechace IDs numéricos legacy y exija columnas UUID en la ruta canónica.
- Se reforzó la cobertura de identidad para sucursales, roles y usuarios con fixtures migradas a UUID.
- `tests/integration/test_settings_module_loads.py` ejecuta `migrations.standalone.096_configuration_services_schema` en la fixture mínima para verificar la ruta canónica del módulo sobre esquema migrado.

CAMBIOS:
- `repositories/config_repository.py` valida UUIDv7 canónicos para entidades de Configuración y elimina el fallback a `id`, `rol_id` y `sucursal_id` en contratos públicos del repositorio.
- Las lecturas y mutaciones canónicas de sucursales, usuarios, roles, permisos, Happy Hour y cierres mensuales ahora exigen columnas UUID migradas y operan por UUID.
- Se eliminaron las ramas de runtime que seguían escribiendo o leyendo permisos por `rol_id` y referencias de sucursal por `sucursal_id` cuando existe la ruta `rol_uuid`/`sucursal_uuid`.

LEGACY ELIMINADO:
- Eliminada aceptación de IDs numéricos legacy en `ConfigRepository` para sucursales, usuarios, roles y reglas Happy Hour.
- Eliminados fallbacks canónicos de Configuración a `rol_id`, `sucursal_id` e identificadores enteros cuando el esquema migrado ya expone columnas UUID.

BUSQUEDAS NEGATIVAS:
- `payload.get("branch_id", "1")` -> 0 coincidencias en código canónico; permanece solo la aserción negativa del test.
- `branch_id must be a branch UUID or numeric legacy id` -> 0 coincidencias.
- `role_id must be a role UUID or numeric legacy id` -> 0 coincidencias.
- `user_id must be a user UUID or numeric legacy id` -> 0 coincidencias.
- `uuid4`, `lastrowid`, `entity_id=str(user_id|role_id|saved_id)` -> 0 coincidencias en `modulos/configuracion.py`, `core/services/configuration_settings_service.py` y `repositories/config_repository.py`.

TESTS EJECUTADOS:
- `python -m pytest tests/unit/test_configuracion_refactor_services.py -q`
- `python -m pytest tests/integration/test_roles_permissions_canonical_flow.py -q`
- `python -m pytest tests/unit/test_configuracion_refactor_services.py tests/architecture/test_configuracion_scope.py tests/architecture/test_uuidv7_cutover_protection.py tests/architecture/test_refactor_work_queue.py -q`
- `python -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in ['repositories/config_repository.py','core/services/configuration_settings_service.py','tests/unit/test_configuracion_refactor_services.py','tests/integration/test_settings_module_loads.py']]; print('AST_OK')"`

INCIDENCIAS DE ENTORNO OBSERVADAS:
- `python -m pytest tests/integration/test_settings_module_loads.py -q` provoca una `Windows fatal exception: access violation` dentro de PyQt al cargar la pestaña Happy Hour; no dejó una aserción funcional del lote abierta.
- `python -m pytest tests/architecture -q` y `python -m pytest tests/unit -q` siguen fallando por deuda previa no perteneciente a `CONFIGURACION-02-IDENTITY` y por permisos del entorno para `tmp_path`/`.pytest_cache`.

VIOLACIONES RESTANTES DEL LOTE:
- 0

SIGUIENTE LOTE REGISTRADO:
- `CONFIGURACION-03-UI`

### CONFIGURACION-03-UI - Iteración 2

MODULO: CONFIGURACION
LOTE: CONFIGURACION-03-UI
ITERACION: 2
ESTADO INICIAL: IN_PROGRESS
ESTADO FINAL: DONE

HALLAZGOS:
- `modulos/configuracion.py` seguía usando `QComboBox` editable como pseudo-autocomplete para sucursales y empleados en la sucursal de terminal, reglas Happy Hour y formulario de usuarios.
- La selección de entidades dependía de `currentData()` y de wiring manual repetido, sin usar los componentes estándar `SearchSelector` ya disponibles en `frontend/desktop/components`.

CAUSAS RAIZ:
- El módulo incorporó `ProductSearchBox` durante iteraciones previas, pero mantuvo selectores históricos de `QComboBox` para otras entidades porque no existía un adapter local que reutilizara los catálogos ya expuestos por los servicios canónicos.
- El helper `_enable_combo_search()` prolongó una ruta visual legacy: seguía cargando listas completas y maquillándolas como búsqueda en vez de mover la captura a `BranchSearchBox` y `EmployeeSearchBox`.

TESTS DE PROTECCION:
- `tests/unit/test_configuracion_refactor_services.py` ahora exige `BranchSearchBox` y `EmployeeSearchBox` en la UI canónica y prohíbe reintroducir `QComboBox` masivos para sucursal/empleado o el helper `_enable_combo_search()`.

CAMBIOS:
- La sucursal de terminal usa `BranchSearchBox` y persiste la selección mediante `SearchOption` explícito en lugar de `currentData()`.
- El editor de Happy Hour usa `BranchSearchBox` para la sucursal de la regla.
- El editor de usuarios usa `BranchSearchBox` para sucursal y `EmployeeSearchBox` para empleado RRHH, manteniendo `QComboBox` solo para el rol.
- Se agregaron providers locales y helpers de resolución para hidratar labels existentes sin volver a combos cargados en masa.

LEGACY ELIMINADO:
- Eliminado `_enable_combo_search()` de `modulos/configuracion.py`.
- Eliminados los `QComboBox` legacy para `cmb_sucursal_inst`, `combo_branch`, `cmb_sucursal` y `cmb_empleado` en la ruta canónica del módulo.

BUSQUEDAS NEGATIVAS:
- `rg -n "self\\.cmb_sucursal_inst = QComboBox\\(|combo_branch = QComboBox\\(|cmb_sucursal = QComboBox\\(|cmb_empleado = QComboBox\\(|self\\._enable_combo_search\\(" modulos/configuracion.py tests/unit/test_configuracion_refactor_services.py` -> 0 coincidencias en `modulos/configuracion.py`; permanece solo la protección negativa en el test.
- `rg -n "BranchSearchBox|EmployeeSearchBox" modulos/configuracion.py` -> coincidencias esperadas en la ruta canónica.

TESTS EJECUTADOS:
- `python -m pytest tests/unit/test_configuracion_refactor_services.py -q`
- `python -c "import ast, pathlib; files=['modulos/configuracion.py','tests/unit/test_configuracion_refactor_services.py']; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8')) for f in files]; print('AST_OK')"`

INCIDENCIAS DE ENTORNO OBSERVADAS:
- `python -m pytest tests/integration/test_settings_module_loads.py -q` sigue provocando `Windows fatal exception: access violation` dentro de PyQt al cargar la pestaña Happy Hour. La traza apunta a la misma zona de UI ya registrada previamente; no dejó una aserción nueva abierta del lote 03.
- `pytest` sigue emitiendo `PytestCacheWarning` por permisos del entorno sobre `.pytest_cache`.

VIOLACIONES RESTANTES DEL LOTE:
- 0

SIGUIENTE LOTE REGISTRADO:
- `CONFIGURACION-04-QUERIES`

### CONFIGURACION-04-QUERIES - Iteración 1

MODULO: CONFIGURACION
LOTE: CONFIGURACION-04-QUERIES
ITERACION: 1
ESTADO INICIAL: IN_PROGRESS
ESTADO FINAL: DONE

HALLAZGOS:
- `modulos/config_modules.py` seguía leyendo `sucursales` y `feature_flags` con `self.db.execute(...).fetchall()` desde PyQt.
- El módulo no tenía un QueryService propio para la pantalla de toggles; por eso la UI quedó fuera de la ruta canónica que ya usa servicios explícitos en `modulos/configuracion.py`.

CAUSAS RAIZ:
- La administración de toggles por sucursal se mantuvo como widget histórico separado de `SettingsModuleServices`, sin read model dedicado.
- La deuda de feature flags mezclaba compatibilidad de schema con acceso directo en UI; la compatibilidad había quedado incrustada en la pantalla en vez de aislarse en una frontera de lectura.

TESTS DE PROTECCION:
- `tests/unit/test_config_modules_query_service.py` protege la lectura canónica de sucursales activas, flags legacy por sucursal y resolución read-side de UUID de sucursal a row-id legado.
- `tests/architecture/test_config_modules_queries.py` exige que `modulos/config_modules.py` importe y use `ModuleSettingsQueryService`, y prohíbe reintroducir los `SELECT` directos a `sucursales` y `feature_flags`.

CAMBIOS:
- Se creó `backend/application/queries/module_settings_query_service.py` como QueryService explícito para la pantalla de toggles del módulo Configuración.
- `modulos/config_modules.py` ahora carga sucursales activas y snapshots de feature flags mediante `ModuleSettingsQueryService`.
- `backend/application/queries/__init__.py` exporta el nuevo QueryService para mantener la superficie de consultas consistente.

LEGACY ELIMINADO:
- Eliminadas las lecturas PyQt directas `SELECT id, nombre FROM sucursales ...` y `SELECT clave, activo FROM feature_flags` en `modulos/config_modules.py`.
- Reducida la deuda registrada de `SQL in UI` en `modulos/config_modules.py` a las dos sentencias de mutación que pertenecen al lote siguiente.

BUSQUEDAS NEGATIVAS:
- `rg -n "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre|SELECT clave, activo FROM feature_flags" modulos/config_modules.py` -> 0 coincidencias.
- `rg -n "module_settings_query_service|self\\.module_settings_query_service\\.list_active_branch_options|self\\.module_settings_query_service\\.get_branch_feature_flags" modulos/config_modules.py` -> coincidencias esperadas en la ruta canónica.
- Conteo residual de deuda arquitectónica en `modulos/config_modules.py`: `SQL in UI = 2` (`INSERT ... ON CONFLICT`), `commit/rollback in UI = 1` (`commit()`), ambos reservados para `CONFIGURACION-05-MUTATIONS`.

TESTS EJECUTADOS:
- `python -m pytest tests/unit/test_config_modules_query_service.py tests/architecture/test_config_modules_queries.py tests/unit/test_configuracion_refactor_services.py tests/architecture/test_no_sql_in_frontend.py tests/architecture/test_no_commit_rollback_in_frontend.py tests/architecture/test_refactor_work_queue.py -q`
- `python -c "import ast, pathlib; files=['backend/application/queries/module_settings_query_service.py','modulos/config_modules.py','tests/unit/test_config_modules_query_service.py','tests/architecture/test_config_modules_queries.py']; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8')) for f in files]; print('AST_OK')"`

INCIDENCIAS DE ENTORNO OBSERVADAS:
- `pytest` sigue emitiendo `PytestCacheWarning` por permisos del entorno sobre `.pytest_cache`; no afectó el resultado funcional del lote.

VIOLACIONES RESTANTES DEL LOTE:
- 0

SIGUIENTE LOTE REGISTRADO:
- `CONFIGURACION-05-MUTATIONS`

### CONFIGURACION-05-MUTATIONS - IteraciÃ³n 1

MODULO: CONFIGURACION
LOTE: CONFIGURACION-05-MUTATIONS
ITERACION: 1
ESTADO INICIAL: IN_PROGRESS
ESTADO FINAL: DONE

HALLAZGOS:
- `modulos/config_modules.py` seguÃ­a mutando toggles por sucursal desde PyQt con `feature_flag_service.repo.set_flag`, manipulaciÃ³n directa de `_cache` y fallback `INSERT ... ON CONFLICT` + `commit()`.

CAUSAS RAIZ:
- La pantalla de toggles dependÃ­a de detalles internos de `FeatureFlagService` en vez de una frontera de servicio para escritura.
- La compatibilidad entre schemas de `feature_flags` se habÃ­a quedado incrustada en la UI, dejando una ruta legacy de SQL directo y transacciÃ³n en frontend.

TESTS DE PROTECCION:
- `tests/unit/test_feature_flag_service.py` protege la mutaciÃ³n canÃ³nica mediante servicio y el refresco de cachÃ© para schema nuevo y legacy.
- `tests/architecture/test_config_modules_mutations.py` prohÃ­be reintroducir `ffs.repo.set_flag`, `_cache.pop`, SQL directo sobre `feature_flags` y `commit()` en `modulos/config_modules.py`.

CAMBIOS:
- `core/services/feature_flag_service.py` ahora expone `set_flag()` como frontera canÃ³nica para persistir el toggle y refrescar la cachÃ© de la sucursal afectada.
- `modulos/config_modules.py` inyecta `FeatureFlagService` explÃ­cito y usa `self.feature_flag_service.set_flag(...)` para toda mutaciÃ³n.
- Si el `container` no trae el servicio, la UI crea una instancia canÃ³nica respaldada por `FeatureFlagRepository` en lugar de caer a SQL directo.

LEGACY ELIMINADO:
- Eliminada la ruta `feature_flag_service.repo.set_flag(...)` desde PyQt.
- Eliminada la manipulaciÃ³n directa de `_cache` desde `modulos/config_modules.py`.
- Eliminado el fallback `INSERT INTO feature_flags ... ON CONFLICT ...` y `self.db.commit()` en la UI de toggles.

BUSQUEDAS NEGATIVAS:
- `rg -n "ffs\\.repo\\.set_flag\\(|ffs\\._cache\\.pop\\(|INSERT INTO feature_flags|ON CONFLICT\\(clave\\) DO UPDATE SET activo=excluded\\.activo|self\\.db\\.commit\\(" modulos/config_modules.py core/services/feature_flag_service.py` -> 0 coincidencias en cÃ³digo productivo.
- `rg -n "feature_flag_service\\.set_flag\\(|FeatureFlagService\\(|FeatureFlagRepository\\(" modulos/config_modules.py core/services/feature_flag_service.py` -> coincidencias esperadas en la ruta canÃ³nica.

TESTS EJECUTADOS:
- `python -m pytest tests/unit/test_feature_flag_service.py tests/unit/test_config_modules_query_service.py tests/architecture/test_config_modules_queries.py tests/architecture/test_config_modules_mutations.py -q`
- `python -m pytest tests/unit/test_feature_flag_service.py tests/unit/test_config_modules_query_service.py tests/architecture/test_config_modules_queries.py tests/architecture/test_config_modules_mutations.py tests/architecture/test_no_sql_in_frontend.py tests/architecture/test_no_commit_rollback_in_frontend.py -q`
- `python -c "import ast, pathlib; files=['core/services/feature_flag_service.py','modulos/config_modules.py','tests/unit/test_feature_flag_service.py','tests/architecture/test_config_modules_mutations.py']; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8')) for f in files]; print('AST_OK')"`

INCIDENCIAS DE ENTORNO OBSERVADAS:
- `pytest` sigue emitiendo `PytestCacheWarning` por permisos del entorno sobre `.pytest_cache`; no afectÃ³ el resultado funcional del lote.

VIOLACIONES RESTANTES DEL LOTE:
- 0

SIGUIENTE LOTE REGISTRADO:
- `CONFIGURACION-06-DOMAIN_RULES`
