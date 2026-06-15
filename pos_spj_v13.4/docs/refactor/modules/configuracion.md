# Módulo CONFIGURACION

## Estado

```text
AUDIT
```

## Iteración

```text
2
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

## Avance de lote activo: CONFIGURACION-02-IDENTITY

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
- CONFIGURACION-02-IDENTITY sigue IN_PROGRESS por identidades enteras persistentes pendientes de migración en esquema/DTO/repositorio.

SIGUIENTE LOTE:
- Continuar CONFIGURACION-02-IDENTITY hasta cerrar PK/FK/DTO/repositorios UUIDv7 sin identidad dual.
