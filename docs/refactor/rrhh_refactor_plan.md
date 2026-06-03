# Plan de refactor seguro por fases — RRHH

## 1. Nueva arquitectura RRHH

Arquitectura objetivo por capas:

```text
UI PyQt actual / ui/rrhh futura
  -> RRHH Application Services
  -> RRHH Domain Services / Policies / Strategies
  -> Repository interfaces
  -> SQLite repository adapters
  -> Database + EventBus post-commit
```

Reglas de transición:

- Las pantallas actuales siguen funcionando durante todo el refactor.
- Cada migración es idempotente y se introduce antes de que el código la use.
- Finanzas solo cambia cuando existan tests de no duplicación e idempotencia.
- Los repositorios nuevos primero replican SQL legacy; después se cablean por pantalla.

## 2. Estructura de carpetas

```text
core/rrhh/
  domain/
    entities.py
    services.py
    policies/
    strategies/
  application/
    repositories.py
    employee_application_service.py
    attendance_application_service.py
    leave_application_service.py
    shift_application_service.py
    payroll_application_service.py
    payroll_payment_application_service.py
  infrastructure/
    sqlite_repositories.py
    sqlite_unit_of_work.py
  events/
    constants.py
    payloads.py
    publisher.py
ui/rrhh/
  employee_page.py
  attendance_page.py
  leave_page.py
  payroll_page.py
  shift_page.py
```

## 3. Nuevas clases y responsabilidades

| Clase | Capa | Responsabilidad |
|---|---|---|
| `Employee` | Domain | Datos canónicos del empleado legacy `personal`. |
| `AttendanceRecord` | Domain | Registro de asistencia legacy. |
| `LeaveRequest` | Domain | Vacaciones/permisos/incapacidades. |
| `PayrollPayment` | Domain | Pago de nómina legacy `nomina_pagos`. |
| `ShiftRole` | Domain | Rol de turno. |
| `ShiftAssignment` | Domain | Asignación de turno. |
| `SQLiteEmployeeRepository` | Infrastructure | Centralizar SQL de `personal`. |
| `SQLiteAttendanceRepository` | Infrastructure | Centralizar SQL de `asistencias`. |
| `SQLiteLeaveRepository` | Infrastructure | Centralizar SQL de `vacaciones_personal`. |
| `SQLitePayrollRepository` | Infrastructure | Centralizar SQL de `nomina_pagos`. |
| `SQLiteShiftRepository` | Infrastructure | Centralizar SQL de `turno_roles` y `turno_asignaciones`. |
| `EmployeeApplicationService` | Application futura | Altas, edición, baja, sucursal y eventos. |
| `AttendanceApplicationService` | Application futura | Check-in/out, faltas, retardos, horas extra. |
| `LeaveApplicationService` | Application futura | Solicitud/aprobación/rechazo y solapamientos. |
| `PayrollApplicationService` | Application futura | Generación, autorización y pago seguro de nómina. |

## 4. Interfaces de repositorios

Fase 1 define estos ports en `core/rrhh/application/repositories.py`:

- `EmployeeRepository`
- `AttendanceRepository`
- `LeaveRepository`
- `PayrollRepository`
- `ShiftRepository`

Los métodos están diseñados para migrar una pantalla a la vez sin reescribir reglas todavía.

## 5. Servicios de dominio

Se introducirán después de estabilizar repositorios:

- `PayrollCalculator`: calcula sueldo base, bonos, deducciones y neto.
- `AttendanceDomainService`: entrada/salida, horas trabajadas y retardo.
- `VacationOverlapPolicy`: impide solapamientos.
- `PayrollEligibilityPolicy`: excluye empleados inactivos.
- `PayrollAuthorizationPolicy`: bloquea pago sin autorización.
- `DoublePaymentPolicy`: impide pagar dos veces un periodo.
- `CommissionPolicy`: calcula y liquida comisiones trazables.
- `DriverCompensationPolicy`: convierte entregas completadas en pago/comisión laboral.

## 6. ApplicationService

Orden de introducción:

1. `EmployeeApplicationService`: envolver `SQLiteEmployeeRepository` y publicar eventos de empleado.
2. `AttendanceApplicationService`: mover check-in/out desde UI.
3. `LeaveApplicationService`: mover vacaciones/permisos y validar solapamientos.
4. `ShiftApplicationService`: mover roles/asignaciones de turno.
5. `PayrollApplicationService`: generar y autorizar nómina.
6. `PayrollPaymentApplicationService`: pago transaccional con Unit of Work y eventos.

## 7. Eventos y payloads

Eventos canónicos mínimos:

| Evento | Payload requerido |
|---|---|
| `EMPLEADO_CREADO` | `employee_id`, `nombre`, `sucursal_id`, `puesto`, `operation_id` |
| `EMPLEADO_ACTUALIZADO` | `employee_id`, `changes`, `usuario`, `operation_id` |
| `EMPLEADO_DESACTIVADO` | `employee_id`, `reason`, `effective_date`, `operation_id` |
| `ASISTENCIA_REGISTRADA` | `attendance_id`, `employee_id`, `fecha`, `tipo`, `hora`, `operation_id` |
| `RETARDO_REGISTRADO` | `employee_id`, `fecha`, `minutes_late`, `operation_id` |
| `FALTA_REGISTRADA` | `employee_id`, `fecha`, `justification_status`, `operation_id` |
| `HORAS_EXTRA_REGISTRADAS` | `employee_id`, `fecha`, `hours`, `rate`, `operation_id` |
| `VACACIONES_SOLICITADAS` | `request_id`, `employee_id`, `date_start`, `date_end`, `operation_id` |
| `VACACIONES_APROBADAS` | `request_id`, `employee_id`, `days`, `operation_id` |
| `PERMISO_APROBADO` | `request_id`, `employee_id`, `paid`, `dates`, `operation_id` |
| `NOMINA_GENERADA` | `payroll_run_id`, `employee_id`, `total`, `period`, `operation_id` |
| `NOMINA_AUTORIZADA` | `payroll_run_id`, `authorized_by`, `operation_id` |
| `NOMINA_PAGADA` | `payroll_payment_id`, `payroll_run_id`, `employee_id`, `total`, `metodo_pago`, `source_module`, `source_id`, `operation_id` |
| `COMISION_GENERADA` | `commission_id`, `employee_id`, `venta_id`, `amount`, `operation_id` |
| `ENTREGA_COMPLETADA_POR_REPARTIDOR` | `order_id`, `driver_id`, `employee_id`, `total`, `delivered_at`, `operation_id` |

## 8. Migraciones necesarias

No se aplican en fase 1. Migraciones futuras, todas idempotentes:

1. `usuarios.personal_id` nullable.
2. `drivers.personal_id` nullable e índice por empleado.
3. `nomina_pagos.operation_id` nullable único cuando exista.
4. `nomina_pagos.source_module/source_id` o tabla canónica `payroll_payments` con vista legacy.
5. `comisiones_acumuladas.empleado_id`, `source_module`, `source_id`, `estado`, índice único por venta/empleado.
6. `payroll_advances` para anticipos laborales; no reutilizar `anticipos` comerciales.
7. `vacaciones_personal.operation_id` y estados normalizados.

## 9. Tests por fase

| Fase | Tests |
|---|---|
| 1 Repositorios | CRUD legacy de empleados, asistencia, vacaciones, nómina y turnos. |
| 2 Wiring UI parcial | Pantallas cargan los mismos datos usando repositorios. |
| 3 Servicios | Unit tests de check-in/out, baja, turnos y vacaciones. |
| 4 Policies | Solapamientos, empleado inactivo, faltas justificadas, horas extra. |
| 5 Eventos | Payloads obligatorios y publicación post-commit. |
| 6 Finanzas | `NOMINA_PAGADA` genera un solo movimiento financiero. |
| 7 Delivery/RRHH | Entrega completada genera una sola comisión/pago de repartidor. |
| 8 Limpieza | Tests de regresión de UI y eliminación de métodos legacy. |

## 10. Checklist de aceptación

- [ ] El sistema arranca después de cada fase.
- [ ] La UI actual sigue usando las mismas tablas y muestra los mismos datos.
- [ ] No hay migraciones destructivas.
- [ ] No se crea una segunda fuente de empleados.
- [ ] No se paga una nómina sin autorización en el nuevo flujo.
- [ ] No se duplica el movimiento financiero de nómina.
- [ ] Todo evento financiero tiene `operation_id`.
- [ ] Comisiones y repartidores quedan vinculados a empleados antes de liquidarse por nómina.

## 11. Riesgos de regresión

- Cambios en SQL de UI pueden alterar filtros o columnas visibles.
- `NOMINA_PAGADA` actual tiene payload incompleto; corregirlo sin idempotencia puede duplicar trazas.
- `drivers` tiene columnas agregadas desde varios puntos; moverlo requiere migración compatible.
- `vacaciones_personal` se crea desde UI legacy; quitarlo antes de migración rompería pantallas.
- Retenciones hardcodeadas pueden cambiar resultados si se mueven sin tests de caracterización.

## 12. Orden exacto de implementación

1. Crear paquete `core/rrhh` con entidades, interfaces y repositorios SQLite sin cablear UI.
2. Agregar tests de repositorios con SQLite en memoria.
3. Cablear solo lecturas de empleados en `modulos/rrhh.py` detrás de fallback legacy.
4. Cablear asistencia detrás de `AttendanceApplicationService` sin cambiar mensajes UI.
5. Cablear vacaciones y añadir validación de solapamiento en modo advertencia, luego bloqueo.
6. Crear migración `usuarios.personal_id` y `drivers.personal_id` nullable.
7. Vincular repartidores y usuarios a `personal` sin borrar datos legacy.
8. Crear `PayrollApplicationService` para generar/autorizar nómina.
9. Crear `PayrollPaymentApplicationService` con UoW, no doble pago y evento canónico.
10. Cambiar Finanzas para consumir solo evento canónico con tests de idempotencia.
11. Integrar comisiones y anticipos laborales a nómina.
12. Mover UI a `ui/rrhh` y eliminar código muerto cuando tests pasen.

## Fase implementada en este cambio

Fase 1: extracción aditiva de repositorios, sin cablear la UI y sin modificar base de datos.

## Fase 2 implementada en este cambio

Fase 2 cablea la pantalla legacy de RRHH hacia los repositorios extraídos en Fase 1 de forma compatible:

- `DialogoEmpleado` carga, crea y actualiza empleados mediante `SQLiteEmployeeRepository`.
- `ModuloRRHH` lista empleados activos y combos de empleados mediante `SQLiteEmployeeRepository`.
- La baja lógica de empleados usa `SQLiteEmployeeRepository.deactivate()` sin cambiar la auditoría ni los mensajes actuales.
- La consulta/registro de asistencia de la pantalla usa `SQLiteAttendanceRepository` manteniendo los mismos textos y evento legacy.
- Vacaciones/permisos usa `SQLiteLeaveRepository` para listar y crear registros, conservando la creación defensiva legacy de la tabla hasta que exista migración formal.

Límites intencionales de Fase 2:

- No se cambió el comportamiento financiero.
- No se agregaron migraciones.
- No se introdujeron eventos nuevos todavía.
- No se eliminó código legacy ni métodos `_ORIG`.

## Fase 3 implementada en este cambio

Fase 3 introduce servicios de aplicación del bounded context RRHH y mueve la UI legacy un nivel arriba:

- `EmployeeApplicationService` encapsula alta, edición, búsqueda, lookup y baja lógica de empleados.
- `AttendanceApplicationService` encapsula consultas de tabla y el flujo legacy de entrada/salida sin cambiar mensajes ni cálculo de horas.
- `LeaveApplicationService` encapsula listado, creación y consulta de solapamientos de vacaciones/permisos, sin activar aún el bloqueo de solapamientos.
- `ShiftApplicationService` queda disponible para la siguiente fase y envuelve roles/asignaciones de turno sin cablear todavía la pantalla de turnos.

Límites intencionales de Fase 3:

- No se cambió el comportamiento financiero.
- No se agregaron migraciones.
- No se publican eventos RRHH nuevos todavía.
- No se aplica todavía validación bloqueante de solapamientos de vacaciones.
- La UI sigue siendo la misma pantalla PyQt legacy; solo cambia el punto de entrada a servicios de aplicación.

## Fase 4 implementada en este cambio

Fase 4 mueve reglas de negocio puntuales fuera de la UI y servicios legacy hacia policies de dominio:

- `AttendanceHoursPolicy` calcula horas trabajadas; la UI ya no calcula horas y `AttendanceApplicationService` delega en la policy.
- `PayrollPeriodPolicy` determina el periodo de nómina legacy de 7 días; `modulos/rrhh.py` deja de calcular `datetime.now() - timedelta(days=7)` directamente.
- `VacationOverlapPolicy` valida solapamientos activos (`aprobado`/`pendiente`) antes de crear vacaciones/permisos.
- `EmployeeEligibilityPolicy` centraliza elegibilidad de empleado activo para nómina; la UI usa `list_payroll_eligible_employees()`.
- `RestDayPolicy` centraliza días consecutivos, descanso sugerido y cobertura mínima para `HRRuleEngine`.

Límites intencionales de Fase 4:

- No se cambió el comportamiento financiero.
- No se agregaron migraciones.
- No se modificó el flujo de autorización/pago de nómina.
- La validación de solapamientos se aplica solo a solicitudes activas y conserva los estados legacy.

## Fase 5 implementada en este cambio

Fase 5 introduce el contrato canónico de eventos RRHH sin tocar la base de datos ni el comportamiento financiero:

- `core/rrhh/events.py` concentra el catálogo RRHH canónico y payloads validados con dataclasses.
- Cada payload exige `operation_id` no vacío para preparar idempotencia en consumidores de Finanzas, Caja, Delivery y Notificaciones.
- `RRHHEventPublisher` encapsula el EventBus existente y publica `payload.to_dict()` con `event_type` canónico.
- `EmployeeApplicationService`, `AttendanceApplicationService` y `LeaveApplicationService` publican eventos desde la capa de aplicación después de persistir por repositorio.
- `modulos/rrhh.py` deja de publicar eventos RRHH directamente desde UI; las pantallas conservan sus mensajes y delegan en servicios.

Límites intencionales de Fase 5:

- No se agregaron migraciones ni columnas `operation_id` todavía.
- No se cambió el flujo financiero de nómina/pagos.
- No se conectaron consumidores financieros; se evita doble procesamiento hasta implementar idempotencia y Unit of Work.
- Los eventos de nómina, anticipos, comisiones y repartidores quedan catalogados pero se publicarán al migrar esos casos de uso a servicios transaccionales.

## Fase 6 implementada en este cambio

Fase 6 conecta RRHH con Finanzas mediante eventos canónicos y elimina el registro financiero directo desde RRHH:

- `RRHHService.procesar_pago_nomina()` ya no llama `registrar_gasto_opex()`; solo persiste `nomina_pagos`, conserva notificaciones y puede publicar `NOMINA_PAGADA` en fallback legacy.
- `GestionarNominaUC` publica `NOMINA_GENERADA` y `NOMINA_PAGADA` con payload unificado (`total`, `neto`, `payroll_payment_id`, `operation_id`) y no registra asientos directos.
- `PayrollFinanceHandler` consume `NOMINA_GENERADA` y `NOMINA_PAGADA`, registra asientos idempotentes en `journal_entries` mediante `operation_id-GEN` y `operation_id-PAID`, y conserva fallback legacy si no existe el servicio canónico.
- La migración idempotente `093_rrhh_payroll_traceability` agrega `nomina_pagos.operation_id`, `source_module` y `source_id`, además de índice único filtrado para impedir doble pago por la misma operación.

Límites intencionales de Fase 6:

- No se cambia el cálculo de nómina ni retenciones.
- No se elimina `nomina_pagos` legacy; se agrega trazabilidad compatible.
- No se conectan todavía anticipos, comisiones ni pagos de repartidores a nómina.
- Los consumidores financieros quedan idempotentes por `operation_id`, pero la conciliación completa Caja/Tesorería queda para fases posteriores.

## Fase 7 implementada en este cambio

Fase 7 refuerza el refactor con pruebas de dominio e integración sin cambiar el comportamiento funcional de la UI:

- Se agregan strategies de conceptos de nómina (`HourlyPayStrategy`, `PercentageStrategy`, `FixedAmountStrategy`, `PayrollConceptCalculator`) para probar cálculo composable sin condicionales por tipo de concepto.
- Se agrega `AttendanceJustificationPolicy` para cubrir la regla: una falta no debe descontarse cuando existe permiso, vacaciones o descanso aplicable.
- Se añaden tests unitarios deterministas para policies de horas, periodo, elegibilidad, descansos, solapamiento de vacaciones/permisos y faltas justificadas.
- Se añade integración SQLite completa de pago de nómina: `RRHHService` persiste `nomina_pagos`, `GestionarNominaUC` publica eventos y `PayrollFinanceHandler` registra trazas en `journal_entries`.
- Se cubre no doble pago ejecutando dos veces la misma nómina con el mismo `operation_id`: queda un solo `nomina_pagos` y dos asientos idempotentes (`GEN`/`PAID`).

Límites intencionales de Fase 7:

- No se cambia el cálculo legacy de nómina; las strategies quedan disponibles para fases posteriores.
- No se migra la UI a nuevas pantallas.
- No se conectan todavía anticipos, comisiones ni repartidores.

## Fase 8 implementada en este cambio

Fase 8 limpia código muerto y elimina mutaciones de esquema desde UI sin retirar funcionalidad:

- Se elimina `_registrar_asistencia_ORIG()` porque el registro actual de asistencia está cubierto por services/tests.
- `modulos/rrhh.py` deja de crear `puestos` y `vacaciones_personal`; esas tablas pasan a migración idempotente.
- `modulos/delivery.py` deja de ejecutar `CREATE TABLE`/`ALTER TABLE`; `_init_tables()` queda como hook compatible sin mutaciones.
- La gestión de repartidores se consolida en `DriverService`/`DriverRepository`; la UI ya no escribe `drivers` directamente ni borra personas, solo crea/actualiza/desactiva mediante el servicio.
- La migración `094_rrhh_delivery_cleanup_schema` crea `puestos`, `vacaciones_personal` y agrega trazabilidad opcional `drivers.personal_id/source_module`.

Límites intencionales de Fase 8:

- No se elimina ninguna tabla legacy.
- No se cambia el flujo de asignación/corte de repartidores.
- No se migra todavía la relación obligatoria repartidor ↔ empleado; se deja columna nullable para migración segura posterior.
