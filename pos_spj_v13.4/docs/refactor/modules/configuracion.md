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

## Siguiente estado

Continuar `CONFIGURACION-02-IDENTITY`.
