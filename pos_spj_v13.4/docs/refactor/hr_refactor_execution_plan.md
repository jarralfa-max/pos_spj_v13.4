# Plan de ejecución — Refactor completo RRHH

Estado: `IN_PROGRESS`

## Skills leídos y prioridad aplicada

1. `docs/skills/SPJ_REFACTOR_SKILL.md` — prioridad absoluta: UUIDv7, born-clean, sin legacy, sin SQL en UI, mutaciones por Use Case, lecturas por QueryService.
2. `docs/skills/SPJ_UI_UX_ARCHITECTURE_SKILL.md` — UI profesional, sin estilos hardcodeados, reubicación a `frontend/desktop/modules` y componentes compartidos.
3. `docs/skills/SPJ_BUGFIX_AUDIT_CORRECTION_SKILL.md` — auditar antes de corregir, tests de protección, no parchar DB viva ni crear migraciones de rescate.

## Alcance de esta fase

Esta Fase 0 no modifica lógica financiera ni de RRHH. Su objetivo es inventariar deuda, rutas legacy y pruebas necesarias antes de crear la implementación canónica.

## Inventario RRHH actual

### UI / navegación legacy

| Archivo | Hallazgo | Riesgo |
| --- | --- | --- |
| `modulos/rrhh.py` | Pantalla PyQt monolítica con empleados, asistencia, nómina, vacaciones, puestos, turnos y reglas. Recibe `db_conn`, usa `container`, construye servicios y conserva PIN por defecto. | Alto: UI conoce infraestructura, calcula/orquesta negocio, usa rutas legacy y estilos locales. |
| `modulos/rrhh_turnos.py` | Módulo PyQt legacy para turnos. | Alto: debe eliminarse tras crear Turnos canónicos. |
| `interfaz/main_window.py` | Importa `ModuloRRHH` y `ModuloRRHHTurnos` desde `modulos`. | Alto: navegación aún apunta a legacy. |
| `core/ui/module_loader.py` | Registra `rrhh` hacia `modulos.rrhh`. | Alto: ruta dinámica legacy. |

### Dominio / servicios legacy

| Archivo | Hallazgo | Riesgo |
| --- | --- | --- |
| `core/rrhh/` | Contiene dominio/aplicación/infraestructura RRHH anterior. | Alto: ubicación incorrecta y contratos no alineados con arquitectura objetivo. |
| `core/services/rrhh_service.py` | Servicio legacy para nómina, retenciones e integración financiera. | Alto: ruta doble respecto a Use Cases nuevos. |
| `core/services/rrhh_catalog_service.py` | Catálogos, KPI y operaciones de vacaciones/turnos llamados desde UI. | Alto: lecturas y mutaciones fuera de QueryService/UseCase canónico. |
| `core/services/rrhh_turnos_service.py` | Servicio de turnos legacy. | Alto: debe sustituirse por dominio `backend/domain/hr`. |
| `core/services/hr_rule_engine.py` | Reglas laborales en `core/services`. | Medio/alto: debe moverse a policies/servicios de dominio HR. |
| `core/use_cases/nomina.py` | Caso de uso de nómina legacy importado por UI y container. | Alto: ruta de nómina paralela. |

## Inventario Caja / Asistencia

| Archivo | Hallazgo | Riesgo |
| --- | --- | --- |
| `backend/application/use_cases/open_cash_shift_use_case.py` | Existe apertura de turno de caja. Debe auditarse para payload `CASH_SHIFT_OPENED` con `user_id` y `employee_id`. | Alto para integración Caja→Asistencia. |
| `backend/application/commands/cash_register_commands.py` | Comandos de caja existentes. | Medio: alinear identidad UUID y empleado vinculado. |
| `application/services/caja_application_service.py` | Servicio legacy de caja. | Medio/alto: confirmar que no llame RRHH directo. |
| `modulos/caja.py` | UI legacy de caja. | Alto si inventa mensajes o controla reglas. |
| `repositories/caja.py` | Repositorio legacy. | Medio: debe revisarse al integrar cierre explícito. |

## Inventario usuarios / permisos / seguridad

| Archivo | Hallazgo | Riesgo |
| --- | --- | --- |
| `backend/application/services/user_security_service.py` | Servicio nuevo de seguridad de usuario. | Medio: posible reutilización para permisos. |
| `backend/application/use_cases/save_user_use_case.py` | Caso de uso de usuarios. | Medio: debe validar `users.employee_id` UUID. |
| `backend/application/use_cases/save_role_permissions_use_case.py` | Permisos por rol. | Medio: base para permisos HR. |
| `core/permissions.py`, `core/security/permission_catalog.py`, `security/rbac.py` | Permisos legacy/catálogo central. | Alto: permisos HR deben registrarse aquí o en catálogo canónico. |
| `repositories/config_repository.py`, `repositories/security_repository.py` | Repositorios de permisos/usuarios legacy. | Alto: revisar casts a int y FKs UUID. |

## Inventario Finanzas / Nómina

| Archivo | Hallazgo | Riesgo |
| --- | --- | --- |
| `core/services/finance/financial_trace_service.py` | Tiene trazabilidad de nómina generada/pagada con payloads `nomina_id` y `empleado_id`. | Alto: debe consumir solo `PAYROLL_PAID` canónico. |
| `core/services/finance/financial_document_service.py` | Documentos tipo `payroll`. | Medio: posible ruta canónica para obligación/pago. |
| `core/services/finance/treasury_service.py` | Lee `nomina_pagos` y calcula egresos de nómina. | Alto: ruta legacy de tabla `nomina_pagos`. |
| `core/events/wiring.py` | Conecta eventos `NOMINA_GENERADA` / `NOMINA_PAGADA`. | Alto: sustituir por `PAYROLL_RUN_GENERATED`/`PAYROLL_PAID`. |
| `backend/infrastructure/db/repositories/finance_read_repository.py` | Lecturas financieras nuevas. | Medio: validar consumo de fuente canónica. |

## Inventario eventos

| Archivo | Hallazgo | Riesgo |
| --- | --- | --- |
| `backend/shared/events/event_names.py` | Catálogo nuevo de eventos. | Debe ampliarse con eventos HR canónicos. |
| `backend/shared/events/event_bus.py`, `event_contracts.py`, `event_dispatcher.py` | Infraestructura nueva de eventos. | Debe usarse para HR. |
| `core/rrhh/events.py` | Eventos legacy RRHH (`NOMINA_*`, `EMPLEADO_*`). | Alto: reemplazar por catálogo canónico. |
| `core/events/` | Bus y handlers legacy. | Alto: evitar nuevas dependencias legacy. |

## Rutas antiguas identificadas

- `modulos/rrhh.py`
- `modulos/rrhh_turnos.py`
- `core/rrhh/`
- `core/services/rrhh_service.py`
- `core/services/rrhh_catalog_service.py`
- `core/services/rrhh_turnos_service.py`
- `core/use_cases/nomina.py`
- Imports desde `interfaz/main_window.py`, `core/ui/module_loader.py`, `core/app_container.py` y `application/use_cases/__init__.py`.
- Tests legacy que importan `core.rrhh`, `rrhh_service` y `core.use_cases.nomina`.

## Tablas relacionadas existentes

Definidas en `migrations/m000_base_schema.py` o migraciones standalone:

- `asistencias`
- `nomina_records`
- `nomina_pagos`
- `turno_roles`
- `turno_asignaciones`
- `turno_notificaciones_log`
- `vacaciones_personal`
- `turnos_caja`
- `turno_actual`

Estas tablas no cumplen el modelo objetivo. Deben sustituirse por esquema canónico HR: `employees`, `departments`, `positions`, `work_shifts`, `shift_assignments`, `attendance_punches`, `attendance_workdays`, `attendance_adjustments`, `leave_requests`, `payroll_runs`, `payroll_lines`, `payroll_concepts`, `payroll_payments`, entre otras.

## Rutas de pago de nómina identificadas

1. UI `modulos/rrhh.py` calcula con `container.rrhh_service.calcular_nomina()` y paga con `container.rrhh_service.procesar_pago_nomina()`.
2. UI intenta usar `container.uc_nomina` / `core.use_cases.nomina.SolicitudNomina`, pero tiene fallback silencioso al servicio legacy.
3. `core/use_cases/nomina.py` publica eventos legacy `NOMINA_GENERADA` y `NOMINA_PAGADA`.
4. Finanzas consume/lee `nomina_pagos` y eventos legacy desde `core/events/wiring.py` y servicios financieros.

Ruta canónica objetivo: `GeneratePayrollRunUseCase` → `AuthorizePayrollRunUseCase` → `PayPayrollRunUseCase` → evento `PAYROLL_PAID` idempotente.

## Accesos directos desde PyQt detectados

- `modulos/rrhh.py` recibe `db_conn` en diálogos y módulo.
- `modulos/rrhh.py` instancia servicios y repositorios de `core.rrhh.infrastructure`.
- `modulos/rrhh.py` consulta servicios de catálogo para KPI, vacaciones, puestos y turnos.
- `modulos/rrhh.py` contiene `setStyleSheet` con colores hardcodeados.
- `modulos/rrhh.py` usa PIN por defecto `1234` vía configuración.
- `modulos/rrhh.py` contiene `pass  # fallback al rrhh_service directo`.

## Orden de implementación recomendado

1. Crear tests de arquitectura HR que documenten infracciones actuales y bloqueen nuevas infracciones.
2. Crear dominio HR, enums, excepciones y puertos con UUIDv7.
3. Crear esquema canónico born-clean en el mecanismo oficial de schema.
4. Crear repositorios y QueryServices.
5. Crear UseCases de empleados, asistencia, turnos, permisos, vacaciones y nómina.
6. Integrar Caja mediante eventos, sin llamadas directas de widgets.
7. Crear UI nueva `frontend/desktop/modules/hr` con presenter y páginas.
8. Actualizar navegación al módulo nuevo.
9. Eliminar legacy RRHH y tests obsoletos.
10. Ejecutar auditorías finales y marcar mapa como `MIGRATED` solo cuando no quede lógica RRHH legacy.

## Tests necesarios por fase

- Arquitectura: no SQL/import sqlite/repos/DB/AppContainer en UI HR; sin RRHH funcional en `modulos/` ni `core/rrhh`.
- UUIDv7: PK/FK `TEXT`, comandos/DTO/eventos sin `int` para IDs.
- Dominio: políticas de asistencia, vacaciones y nómina.
- Infraestructura: repositorios SQLite temporal, FK y constraints.
- Integración: Caja abre/cierra asistencia mediante eventos.
- Nómina: generación, autorización, pago idempotente, no doble movimiento financiero.
- UI: render básico, estados vacíos, permisos, acciones deshabilitadas.

## Reglas satisfechas en Fase 0

- Se leyó la documentación de Skills antes de modificar archivos.
- No se modificó lógica de negocio ni financiera.
- No se crearon migraciones de rescate.
- Se creó este plan en la ruta interna correcta `pos_spj_v13.4/docs/refactor/`.
- Se identificaron rutas legacy, tablas actuales, accesos PyQt directos y rutas dobles de nómina.

## Avance Fase 1 — Dominio y esquema limpio

Se inició la Fase 1 con una base canónica nueva, sin modificar aún navegación legacy ni lógica financiera:

- Creado `backend/domain/hr` con entidades, enums, value objects, excepciones específicas, puertos de repositorio, policies y servicios de dominio.
- Creado `backend/infrastructure/db/schema/hr_schema.py` con sentencias canónicas born-clean para las tablas HR objetivo y PK `id TEXT NOT NULL PRIMARY KEY`.
- Agregados eventos HR canónicos mínimos en `backend/shared/events/event_names.py`, incluyendo empleados, asistencia, turnos, permisos, nómina y cierre de caja.
- Agregados tests focalizados de UUIDv7, schema y arquitectura HR para bloquear nuevas regresiones de identidad y estructura.

Pendiente antes de cerrar Fase 1:

- Integrar `create_hr_schema()` al mecanismo oficial de creación de schema si corresponde.
- Eliminar definiciones RRHH antiguas del schema base solo cuando exista cobertura suficiente y no se rompa arranque.
- Agregar pruebas de FK/constraints más profundas para todos los flujos HR.

## Avance Fase 2 — Infraestructura y Query Services iniciales

Se inició la Fase 2 sin modificar UI legacy ni rutas financieras:

- Creados repositorios SQLite canónicos para empleados, departamentos, puestos, asistencia, ajustes de asistencia, turnos, vacaciones/permisos, corridas de nómina y pagos de nómina.
- Creados DTOs de empleados, asistencia, vacaciones/permisos, nómina y dashboard HR.
- Creados QueryServices de lectura para empleados HR, asistencia, vacaciones/permisos, nómina y dashboard HR.
- Agregada prueba de integración con SQLite temporal para validar roundtrip de repositorios y lectura mediante QueryServices sin exponer DB a UI.

Pendiente antes de cerrar Fase 2:

- Completar filtros/paginación en todos los QueryServices.
- Profundizar pruebas de repositorios para asistencia, turnos, vacaciones y nómina.
- Validar compatibilidad SQL futura con PostgreSQL antes de integrar al arranque canónico.

## Cierre operativo Fase 1 — Schema canónico integrado

Fase 1 queda cerrada para el alcance actual del corte born-clean:

- `migrations/m000_base_schema.py` delega la creación RRHH a `create_hr_schema()`.
- Una base nueva crea las tablas HR canónicas y ya no crea tablas RRHH legacy como `personal`, `asistencias`, `nomina_records`, `nomina_pagos`, `turno_roles` o `turno_asignaciones`.
- Se agregó prueba de integración de corte de schema base para asegurar que el nacimiento de DB sea HR canónico.

La eliminación de lógica runtime legacy continúa pendiente para fases posteriores, cuando UseCases/UI/integraciones canónicas estén funcionales y cubiertas por tests.

## Cierre operativo Fase 2 — Infraestructura y Query Services

Fase 2 queda cerrada para el alcance actual previo a UseCases:

- Repositorios SQLite HR cubren empleados, catálogos base, asistencia, ajustes, turnos, vacaciones/permisos, nómina y pagos.
- QueryServices HR cubren empleados, asistencia, vacaciones/permisos, nómina y dashboard con paginación básica `limit/offset` y filtros iniciales.
- Tests de integración validan roundtrip de repositorios, idempotencia por `operation_id` en solicitudes/pagos y lectura desde QueryServices.
- Guardrails HR verifican que repositorios y queries no reintroduzcan `lastrowid`, `AUTOINCREMENT`, `INTEGER PRIMARY KEY`, DDL ni casts `int(..._id)`.

Siguiente paso permitido: iniciar Fase 3 con Commands/UseCases de empleados, catálogos y permisos, sin tocar UI legacy hasta que exista cobertura de aplicación.

## Avance Fase 3 — Empleados, catálogos y permisos backend

Se inició Fase 3 sin tocar UI legacy:

- Creados Commands canónicos para alta, edición y baja de empleados.
- Creados UseCases `CreateEmployeeUseCase`, `UpdateEmployeeUseCase` y `DeactivateEmployeeUseCase` con autorización central por permisos `hr.employee.*`.
- Los UseCases persisten por `EmployeeRepositoryPort` y publican eventos canónicos `EMPLOYEE_CREATED`, `EMPLOYEE_UPDATED` y `EMPLOYEE_DEACTIVATED` después de guardar.
- El schema base de `usuarios` ahora incluye `employee_id TEXT` para vincular usuarios con empleados por UUID.
- El catálogo central de permisos incluye las acciones HR requeridas por el prompt maestro.

Pendiente para cerrar Fase 3:

- Completar UseCases/catálogos configurables de puestos, departamentos, tipos de contrato y periodicidades.
- Integrar auditoría canónica de alta/edición/baja.
- Crear la nueva UI de Personal bajo `frontend/desktop/modules/hr` y actualizar navegación solo cuando existan pruebas suficientes.

## Avance Fase 3 — Catálogos configurables backend

Se amplió Fase 3 backend sin tocar UI legacy:

- El schema HR incluye catálogos configurables `contract_types` y `payment_frequencies`, además de departamentos y puestos.
- Se agregaron repositorios y QueryService para catálogos HR configurables.
- Se agregaron UseCases para crear departamentos, puestos, tipos de contrato y periodicidades de pago con permiso `hr.settings.manage`.
- Las mutaciones de catálogos publican `HR_CATALOG_UPDATED` después de persistir.

Pendiente para cerrar Fase 3:

- Integrar auditoría canónica de alta/edición/baja y cambios de catálogos.
- Crear la nueva UI de Personal bajo `frontend/desktop/modules/hr` y actualizar navegación solo cuando existan pruebas suficientes.

## Avance Fase 3 — Auditoría canónica de empleados y catálogos

Se completó la instrumentación de auditoría backend de Fase 3 sin acoplar los UseCases a tablas legacy ni a infraestructura concreta:

- Se agregó el puerto `HRAuditSink` y el DTO `HRAuditRecord` para registrar evidencia estructurada desde la capa de aplicación.
- `CreateEmployeeUseCase`, `UpdateEmployeeUseCase` y `DeactivateEmployeeUseCase` emiten auditoría después de persistir y después de publicar el evento canónico.
- Los UseCases de catálogos configurables (`departments`, `positions`, `contract_types`, `payment_frequencies`) emiten auditoría `HR_CATALOG_UPDATED` con metadatos del catálogo modificado.
- Las pruebas de integración de empleados y catálogos validan publicación de eventos y emisión de auditoría sin depender de servicios legacy.

Pendiente para cerrar Fase 3:

- Crear la nueva UI de Personal bajo `frontend/desktop/modules/hr` y actualizar navegación solo cuando existan pruebas suficientes.
- Mantener `modulos/rrhh.py` sin parches superficiales hasta que la navegación pueda apuntar a la nueva UI canónica.

## Avance Fase 3 — UI canónica inicial de Personal

Se agregó la estructura frontend objetivo de RRHH sin conectar navegación legacy ni permitir acceso directo a base de datos desde PyQt:

- Creado `frontend/desktop/modules/hr` con `HRView`, presenter port, rutas y view models.
- Creada navegación interna lateral con secciones Resumen, Personal, Asistencia, Turnos, Vacaciones y permisos, Nómina, Evaluaciones y Configuración.
- La página Personal renderiza columnas empresariales sin exponer UUID al usuario y delega acciones al presenter.
- La página Resumen consume KPI desde el presenter para evitar cálculos en UI.
- Se agregaron shells de páginas/diálogos objetivo para mantener la estructura canónica, sin implementar lógica de fases futuras.
- Se agregó guardrail de arquitectura para verificar que la UI HR objetivo exista y no ejecute SQL, no use transacciones ni conozca `AppContainer`.

Pendiente para cerrar Fase 3:

- Conectar la navegación principal al nuevo `HRView` mediante el mecanismo canónico de la aplicación, sin conservar wrappers con lógica.
- Mantener pruebas de humo UI cuando exista wiring real de presenter/container.

## Avance Fase 3 — Wiring canónico de navegación RRHH

Se conectó la navegación principal al módulo HR canónico sin modificar lógica de negocio legacy:

- `interfaz/main_window.py` importa `CanonicalHRModule` desde `core.ui.hr_module_factory` en lugar de `modulos.rrhh`.
- `core/ui/module_loader.py` resuelve `rrhh` hacia `core.ui.hr_module_factory.CanonicalHRModuleFromConnection`.
- La factory arma `HRView` con `HRDesktopPresenter`, `HREmployeeQueryService` y `HRDashboardQueryService`; la UI HR sigue sin recibir conexión, repositorios ni `AppContainer`.
- Se agregó guardrail para impedir que la navegación principal vuelva a apuntar a `modulos.rrhh`.

Pendiente para cerrar Fase 3:

- Implementar los diálogos reales de alta/edición/baja de empleado contra UseCases canónicos.
- Validar smoke UI con Qt cuando el entorno permita ejecutar widgets con display/offscreen.

## Avance Fase 3 — Diálogo canónico de empleado

Se implementó el primer diálogo funcional de Personal sin catálogos hardcodeados en PyQt:

- `HREmployeeDialog` captura datos de alta/edición y recibe departamentos, puestos, tipos de contrato y periodicidades desde `HREmployeeFormOptionsViewModel`.
- La página Personal abre el diálogo y envía el formulario al presenter mediante `submit_create_employee` o `submit_update_employee`.
- `HRDesktopPresenter` obtiene opciones configurables desde `HRCatalogQueryService` y mantiene la UI desacoplada de repositorios y conexión.
- Se agregó guardrail para impedir que el diálogo vuelva a hardcodear enums de contrato o periodicidad en la UI.

Pendiente para cerrar Fase 3:

- Conectar `submit_create_employee` y `submit_update_employee` con UseCases canónicos y contexto de usuario/operación real.
- Agregar pruebas de humo Qt del diálogo cuando el entorno de ejecución permita widgets offscreen de forma estable.

## Avance Fase 3 — Submit de Personal hacia UseCases

Se conectó el submit de Personal a UseCases canónicos manteniendo la composición fuera de la UI:

- `core.ui.hr_module_factory` arma callbacks de alta/edición que ejecutan `CreateEmployeeUseCase` y `UpdateEmployeeUseCase` con `SQLiteEmployeeRepository`.
- El contexto de usuario/sucursal y permisos se toma de `SessionContext`; la UI HR no recibe sesión, conexión ni repositorios.
- Cada submit genera `operation_id` con `new_uuid()` y valida permisos mediante `session.tiene_permiso`.
- El factory evita importar PyQt en import-time para permitir pruebas headless de la composición de UseCases.
- Se agregó prueba de integración que valida alta de empleado desde el wiring desktop y denegación por permisos insuficientes.

Pendiente para cerrar Fase 3:

- Prefill real de edición de empleado antes de abrir el diálogo de actualización.
- Baja/desactivación desde menú contextual de fila con confirmación amigable.

## Cierre operativo Fase 3 — Personal canónico integrado

Fase 3 queda cerrada para el alcance de empleados, catálogos, permisos y UI Personal:

- La edición de empleado precarga datos desde `HREmployeeQueryService.get_employee` antes de abrir el diálogo.
- La página Personal usa menú contextual por fila para editar o dar de baja, evitando múltiples botones grandes.
- La baja solicita motivo obligatorio y ejecuta `DeactivateEmployeeUseCase` desde la composición canónica.
- Los flujos de alta, edición y baja pasan por UseCases, permisos centrales, `operation_id` UUIDv7 y repositorio canónico.
- Los catálogos de departamento, puesto, tipo de contrato y periodicidad llegan desde QueryServices, no desde listas hardcodeadas en PyQt.

Estado Fase 3: CERRADA.
Siguiente fase permitida: Fase 4 — Asistencia manual y jornada, siempre iniciando con tests y sin tocar Caja todavía.

## Cierre operativo Fase 4 — Asistencia manual y jornada

Fase 4 queda cerrada para el alcance de asistencia manual, jornadas calculadas, ajustes e incidencias, sin avanzar a integración Caja:

- Se agregó `backend/application/commands/attendance_commands.py` con comandos explícitos para registrar marcaciones, registro manual, recálculo de jornada y ajustes.
- `RegisterAttendancePunchUseCase` crea marcaciones inmutables, recalcula la jornada desde `RecalculateWorkdayUseCase` y emite eventos canónicos después de persistir.
- `RegisterManualAttendanceUseCase` exige `hr.attendance.register_manual` y motivo obligatorio antes de delegar a la marcación canónica con source `MANUAL`.
- Se agregaron incidencias canónicas `attendance_incidents` para `MISSING_ENTRY` y `DUPLICATE_IGNORED`; no se inventan entradas cuando hay salida sin entrada.
- Se implementaron repositorios de lectura/escritura para punch por operación, fuente, jornada, incidencias, workday y ajustes.
- `RequestAttendanceAdjustmentUseCase` y `ApproveAttendanceAdjustmentUseCase` preservan la marcación original y registran la corrección como evidencia auditable.
- `AttendanceQueryService` expone workdays con origen e incidencias pendientes para UI; `HRDashboardQueryService` cuenta incidencias desde la tabla canónica.
- La página Asistencia bajo `frontend/desktop/modules/hr/pages/attendance_page.py` renderiza tabla empresarial y registra asistencia manual mediante presenter, sin SQL ni repositorios en PyQt.
- `core.ui.hr_module_factory` compone `AttendanceQueryService` y `RegisterManualAttendanceUseCase` fuera de la UI y genera `operation_id` con `new_uuid()`.
- Las pruebas de integración validan entrada manual, salida manual, duplicado de entrada, salida sin entrada, permiso insuficiente, solicitud/aprobación de ajuste e inmutabilidad del punch original.

Estado Fase 4: CERRADA.
Siguiente fase permitida: Fase 5 — Integración Caja–Asistencia. No iniciar Fase 5 hasta inspeccionar caja, eventos y pruebas de apertura/cierre.

## Cierre operativo Fase 5 — Integración Caja–Asistencia

Fase 5 queda cerrada para el alcance de integración caja-asistencia por eventos, sin iniciar turnos laborales avanzados:

- `OpenCashShiftCommand` acepta `employee_id` y `CashRegisterApplicationService.open_shift` resuelve obligatoriamente `users.employee_id` usando `user_id`; si el usuario no está activo, no está vinculado o no pertenece a la sucursal, bloquea la apertura.
- La identidad funcional de caja ahora usa `user_id` para abrir/buscar/cerrar turno; `user_name` queda como dato de despliegue/compatibilidad de comando, no como identidad funcional.
- Se agregó `CloseCashShiftCommand` y `CloseCashShiftUseCase`; el cierre de turno de caja es explícito y publica `CASH_SHIFT_CLOSED` separado del evento `CASH_Z_CUT_GENERATED`.
- Se agregaron handlers `CashShiftOpenedAttendanceHandler` y `CashShiftClosedAttendanceHandler`, que consumen `CASH_SHIFT_OPENED`/`CASH_SHIFT_CLOSED` y registran `ENTRY`/`EXIT` vía `RegisterAttendancePunchUseCase` con source `CASH_REGISTER`.
- `core.app_container` registra los handlers HR en el EventBus canónico de Caja y conserva la composición fuera de widgets PyQt.
- `modulos/caja.py` invoca `OpenCashShiftUseCase` con `user_id` y usa `CloseCashShiftUseCase` para el cierre explícito, mostrando los mensajes devueltos por el resultado del caso de uso.
- Las pruebas cubren apertura→entrada, cierre→salida, apertura repetida sin duplicado, cierre sin entrada→incidencia, entrada manual previa sin duplicado, múltiples turnos sin múltiples jornadas y bloqueo de usuario sin empleado vinculado.

Estado Fase 5: CERRADA.
Siguiente fase permitida: Fase 6 — Turnos laborales. No iniciar Fase 6 hasta inspeccionar `modulos/rrhh_turnos.py`, turnos legacy y pruebas de cálculo de retardos/extra.

## Cierre operativo Fase 6 — Turnos laborales

Estado: CLOSED.

Problema detectado: la programación de turnos seguía dependiendo de `modulos/rrhh_turnos.py` y `core.services.rrhh_turnos_service`, con una ruta UI→servicio→DB legacy fuera de la arquitectura canónica.

Implementación ejecutada:
- Se consolidaron `WorkShift`, `ShiftAssignment`, `ShiftTemplate` y `RestDay` dentro del dominio HR con identidad UUIDv7.
- Se agregó esquema canónico born-clean para plantillas de turno y descansos.
- Se implementaron repositorio, QueryService y casos de uso para crear turnos, asignar turnos, crear plantillas y registrar descansos.
- Las tolerancias, retardos y horas extra se calculan en policy de dominio (`ShiftPolicy`).
- La UI canónica de Turnos lee únicamente desde presenter/QueryService.
- Se eliminó `modulos/rrhh_turnos.py`; la navegación legacy ya no lo importa.

Validación de fase:
- Tests unitarios/integración/arquitectura HR ejecutados correctamente.
- Tests específicos de turnos validan creación, plantillas, asignaciones, descansos, eventos y cálculo de retardo/horas extra.

Siguiente fase permitida: Fase 7 — Vacaciones y permisos.

## Cierre operativo Fase 7 — Vacaciones y permisos

Estado: CLOSED.

Problema detectado: vacaciones y permisos sólo tenían tabla y lectura parcial; no existía flujo canónico completo de solicitud, aprobación, rechazo, cancelación, historial, auditoría ni validación de solapamientos/saldos dentro del bounded context HR.

Implementación ejecutada:
- Se agregaron comandos y casos de uso canónicos para solicitar, aprobar, rechazar y cancelar permisos.
- Se reforzó el repositorio de permisos con lectura por operación, actualización de estado, validación de solapamientos, saldos y escritura de historial.
- Se añadieron tablas born-clean `leave_balances` y `leave_request_history` con identidad `TEXT NOT NULL PRIMARY KEY`.
- `LeavePolicy` valida rangos, días solicitados, solapamientos y saldo disponible.
- La aprobación descuenta saldo de vacaciones de forma explícita; la solicitud valida saldo antes de quedar pendiente.
- Se agregó auditoría y eventos para solicitud, aprobación, rechazo y cancelación.
- La UI canónica de Vacaciones y permisos lee únicamente desde presenter/`LeaveQueryService`.

Validación de fase:
- Tests específicos de permisos validan solicitud, aprobación, rechazo, cancelación, historial, auditoría, eventos, solapamientos y saldo insuficiente.
- Tests unitarios/integración/arquitectura HR ejecutados correctamente.

Siguiente fase permitida: Fase 8 — Nómina.

## Cierre operativo Fase 8 — Nómina

Estado: CLOSED.

Problema detectado: la nómina legacy conservaba una ruta doble (`core/use_cases/nomina.py` → `rrhh_service`) con fallback desde `modulos/rrhh.py`, mezclando cálculo, autorización y pago en un flujo acoplado e incompatible con la arquitectura HR canónica.

Implementación ejecutada:
- Se agregaron comandos y casos de uso canónicos separados para generar, autorizar, pagar y cancelar corridas de nómina.
- La generación crea `PayrollRun`, `PayrollLine` y conceptos `BASE_SALARY` mediante `PayrollCalculator`/policies de dominio.
- La autorización y el pago son pasos separados y protegidos por `hr.payroll.authorize` y `hr.payroll.pay`.
- El pago es idempotente por `operation_id`, bloquea doble pago por corrida y publica un único evento `PAYROLL_PAID` para integración financiera.
- `PayrollPolicy` bloquea pago sin autorización, doble pago, cancelación de corridas pagadas y estados inválidos.
- La UI canónica de Nómina lee desde presenter/`PayrollQueryService`; la ruta legacy en `modulos/rrhh.py` queda deshabilitada para evitar rutas dobles.
- Se eliminó `core/use_cases/nomina.py` y sus tests legacy directos.

Validación de fase:
- Tests específicos de nómina validan generación, líneas, conceptos, autorización, pago, pago sin autorización, doble pago, idempotencia y no duplicación del evento financiero.
- Tests unitarios/integración/arquitectura HR ejecutados correctamente.

Siguiente fase permitida: Fase 9 — UI/UX empresarial.

## Cierre operativo Fase 9 — UI/UX empresarial

Estado: CLOSED.

Problema detectado: la UI canónica de RRHH ya estaba separada por presenter, pero varias páginas sólo tenían tablas básicas sin estados vacíos/carga, sin paginación, con filtros inmediatos sin debounce y con navegación secundaria mínima. Además, el badge compartido mantenía colores hardcodeados incompatibles con tema claro/oscuro.

Implementación ejecutada:
- Se reforzó la navegación lateral interna con nombres empresariales sin emojis, tooltips, tamaño mínimo validable para uso dentro de resolución 1366×768 y accesibilidad básica.
- Se convirtió el dashboard en un tablero de KPI con tarjetas theme-neutral; todos los valores siguen viniendo desde `HRDashboardQueryService` vía presenter.
- Se agregaron componentes estándar en `frontend/desktop/components/`: `DebouncedSearchInput`, `EmptyState`, `LoadingState` y `PaginationBar`.
- Se eliminaron colores y estilos locales del `StatusBadge`; ahora sólo expone propiedades semánticas para que el tema activo aplique claro/oscuro.
- Personal, Asistencia, Turnos, Vacaciones y Nómina incorporan estados vacíos, loading states, tooltips y paginación por offset/limit.
- Personal usa filtro con debounce para no disparar lecturas en cada tecla.
- Las tablas no muestran UUIDs funcionales y conservan acciones por menú contextual o botones secundarios por fila.

Validación de fase:
- Tests de arquitectura validan navegación lateral, estados vacíos, loading, paginación, debounce y ausencia de estilos/colores hardcodeados en la UI HR.
- Compilación de la UI HR y componentes compartidos completada correctamente.

Siguiente fase permitida: Fase 10 — Eliminación final de legacy.

## Cierre operativo Fase 10 — Eliminación final de legacy

Estado: CLOSED.

Problema detectado: después de la UI/UX empresarial aún quedaban archivos runtime legacy de RRHH en `modulos/`, `core/rrhh/`, `core/services/` y migraciones standalone de rescate. También persistían imports indirectos en contenedor/event wiring que podían reactivar rutas obsoletas.

Implementación ejecutada:
- Se eliminaron los módulos legacy `modulos/rrhh.py` y `modulos/rrhh_turnos.py`.
- Se eliminó `core/rrhh/` y los servicios antiguos de RRHH (`rrhh_service`, catálogos, turnos y rule engine legacy).
- Se eliminaron migraciones standalone antiguas de RRHH que transformaban esquemas previos; la base nueva nace desde `backend/infrastructure/db/schema/hr_schema.py`.
- Se eliminó el plan legacy `docs/refactor/rrhh_refactor_plan.md`.
- Se limpiaron imports y wiring de contenedor/eventos que apuntaban a servicios RRHH legacy.
- Se eliminaron tests legacy que caracterizaban `core.rrhh`, servicios antiguos, turnos legacy y nómina legacy.
- Se añadieron guardrails para confirmar que no quedan rutas runtime nuevas dependiendo de carpetas legacy.

Validación de fase:
- Tests de arquitectura HR validan que los archivos legacy no existen y que runtime (`backend`, `core`, `frontend`, `interfaz`, `application`, `modulos`) no importa rutas RRHH legacy.
- Tests unitarios/integración/arquitectura HR ejecutados correctamente tras la eliminación.

Siguiente fase permitida: Fase 11 — Validación final.

## Cierre operativo Fase 11 — Validación final

Estado: MIGRATED.

Validación ejecutada:
- Tests unitarios HR ejecutados sobre `tests/unit/hr`.
- Tests de integración HR ejecutados sobre `tests/integration/hr`.
- Tests de arquitectura HR ejecutados y auditoría de arquitectura global registrada.
- Tests e2e críticos agregados y ejecutados en `tests/e2e/hr` para confirmar eliminación de rutas legacy y nacimiento de esquema canónico.
- Auditoría de imports legacy RRHH ejecutada contra runtime (`backend`, `core`, `frontend`, `interfaz`, `application`, `modulos`).
- Auditoría UUIDv7 ejecutada contra rutas HR canónicas.
- Auditoría de SQL en UI ejecutada contra `frontend/desktop/modules/hr`.
- Auditoría de estilos hardcodeados ejecutada contra `frontend/desktop/modules/hr` y componentes desktop compartidos relevantes.
- Auditoría de `except Exception: pass` ejecutada contra rutas HR canónicas.
- Auditoría de rutas duplicadas ejecutada para confirmar ausencia de `modulos.rrhh`, `core.rrhh`, servicios RRHH legacy, `uc_nomina` y eventos legacy de nómina/RRHH.

Resultado de migración:
- `modulos/rrhh.py` no existe.
- `modulos/rrhh_turnos.py` no existe.
- `core/rrhh/` no existe.
- Servicios RRHH legacy y `core/use_cases/nomina.py` no existen.
- Las rutas nuevas dependen del bounded context canónico `backend/application/use_cases/hr`, `backend/application/queries`, `backend/infrastructure/db/repositories`, `backend/infrastructure/db/schema/hr_schema.py` y `frontend/desktop/modules/hr`.
- El módulo se marca como `MIGRATED` porque no queda lógica funcional de RRHH en carpetas legacy.

Notas de ejecución Fase 11:
- La validación focalizada HR (`tests/unit/hr`, `tests/integration/hr`, `tests/architecture/test_hr_architecture.py`, `tests/e2e/hr`) pasó completa.
- Las suites globales `tests/unit`, `tests/integration` y `tests/architecture` se ejecutaron como auditoría ampliada y mantienen fallos ajenos al cierre RRHH canónico (Configuración, Inventario, Delivery, orquestador de refactor y PK TEXT históricas). Esos fallos no reintroducen rutas RRHH legacy ni bloquean el estado `MIGRATED` de RRHH.
