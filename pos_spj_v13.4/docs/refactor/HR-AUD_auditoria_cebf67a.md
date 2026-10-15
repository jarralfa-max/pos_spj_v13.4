# HR-AUD — Respuesta a la auditoría directa de RR. HH. (cebf67a)

Fecha: 2026-10-14. Auditoría recibida: «Auditoría directa del módulo de Recursos
Humanos» (31 hallazgos, 36 escenarios, base 155/156). Cada hallazgo se volvió a
comprobar contra el árbol actual (que ya incluía el cableado RR. HH.→Finanzas de
FIN-AUD) y se corrigió o se deja abierto con su motivo.

Migraciones: **335** (esquema) y **336** (permisos `RRHH.*`). Verificadas sobre
copia de la base real: aplican limpias y son idempotentes.
Pruebas nuevas: `tests/integration/hr/test_audit_hr_cebf67a.py` (41) y
`tests/integration/finance/test_hr_payroll_contract.py` (3).

## Hallazgo adicional (no estaba en el informe)

La sesión viva (`LegacySessionAdapter`) expone `active_branch_id`/`sucursal_id`,
**no** `branch_id`. El presentador de RR. HH. leía `branch_id`, así que en
producción **nunca** filtraba por sucursal, y el registro manual de asistencia y
las solicitudes de ausencia **fallaban siempre** con «No hay sucursal». El
auditor probó con una sesión de prueba que sí traía `branch_id`. Ahora la
sucursal sale de `session_branch_id()` (`backend/application/hr/session_authorization.py`).
En la base real hay 0 empleados: nadie había podido darlos de alta desde la UI.

## Decisiones tomadas por defecto (revisables)

| Tema | Decisión | Dónde cambiarla |
|---|---|---|
| Permisos sembrados (HR-01) | system_owner, admin y gerente: todas las `RRHH.*` (ya operaban el módulo con las gruesas); solo_lectura: sólo consulta. Las gruesas quedan inertes (regla del catálogo, como Inventario 179). | Matriz de permisos / migración 336 |
| Alcance (HR-02) | Sucursal activa siempre; asignadas con `RRHH.ver.sucursales_asignadas`; cualquiera o corrida de todas con `RRHH.ver.todas_sucursales`. Igual que Compras/Caja. | `HRSessionPermissionChecker` |
| Política salarial (HR-07) | Sueldo fijo (todo contrato salvo HOURLY): días de vigencia × tarifa del día; se descuentan permisos sin goce y **faltas contra turno asignado**. Por horas: minutos trabajados + días con goce. | `PayrollCalculator` |
| Pago de ausencias (HR-08) | Vacaciones, permiso con goce y falta justificada: pagados. Permiso sin goce e **incapacidad**: descontados (la incapacidad la cubre el IMSS). | `LEAVE_PAY_POLICY` en `payroll_use_cases.py` |
| Asistencia pendiente (HR-07) | Jornadas abiertas/con incidencia o ajustes pendientes en el periodo **bloquean la autorización** (`PENDING_ATTENDANCE`); se resuelven y se regenera. | `AuthorizePayrollRunUseCase` |
| Salida fuera de secuencia (HR-14) | Una salida sin entrada abierta queda como evidencia e incidencia `OUT_OF_SEQUENCE` y no suma horas. Consecuencia: con dos cajas, cerrar la segunda genera incidencia a revisar. | `WorkdayBuilder` |
| Descanso (HR-15) | `break_minutes` del turno = descanso **no pagado**, descontado del trabajado y del esperado (sin doble descuento si ya marcó la comida). | `WorkShift.expected_minutes` |
| Turno nocturno (HR-13) | Una salida pertenece a la jornada con entrada abierta si llega dentro de 20 h. | `AttendancePolicy.MAX_OPEN_WORKDAY_HOURS` |
| Zona horaria (HR-22) | Perfil de sucursal → zona de la empresa → America/Mexico_City. Hora capturada sin zona = hora local de la sucursal. Se declaró `tzdata` en requirements. | `HRCalendarRepository` |
| Vacaciones (HR-18) | Saldo por **ciclo de aniversario**, derecho según la tabla LFT 2023 (12, +2 por año hasta 20; luego +2 cada 5), disponible desde el inicio del ciclo (como antes). No es certificación legal. | `vacation_entitlement` |
| Usuario sin empleado en caja (HR-06) | La apertura/cierre de caja NO se bloquea (nadie está vinculado en la base real); el evento queda retenido en `hr_inbox` y se aplica al vincular. | `cash_attendance_handlers.py` |
| Pago en efectivo (HR-29) | Acredita Caja (1101); transferencia y cheque, Bancos (1110). Transferencia/cheque exigen referencia; el diálogo pide confirmar el importe. | `PayrollPaidHandler._payment_account` |

## Hallazgo por hallazgo

| # | Pri. | Estado | Qué se hizo | Prueba |
|---|---|---|---|---|
| HR-01 | P0 | Cerrado | `AuthorizationPolicy` falla cerrada; vocabulario `RRHH.<accion>` (25 códigos) en el catálogo central; `build_hr_presenter` liga TODOS los casos de uso a `HRSessionPermissionChecker`; sin sesión no hay actor (se quitó `"desktop"`); lecturas por permiso; botones según capacidades. | `TestHR01Authorization`, `test_live_hr_composition_wires_session_authorization` |
| HR-02 | P1 | Cerrado | Toda lectura filtra por la sucursal de la sesión; todo comando por ID valida la sucursal del documento (`require_branch`). | `TestHR02BranchScope` |
| HR-03 | P0 | Cerrado | `wire_cash_attendance` en el arranque (CASH_SHIFT_OPENED/CLOSED → asistencia); el Corte Z ahora publica `CASH_SHIFT_CLOSED` con el cajero (nadie lo emitía); ambos son de consumo obligatorio en el `cash_outbox`. Nómina→Finanzas ya estaba cableada (FIN-AUD). | `test_cash_shift_events_have_consumers`, `test_hr_payroll_contract.py` |
| HR-04 | P1 | Cerrado | El sobre de PAYROLL_PAID lleva el mismo `event_id` que su fila de outbox, `occurred_at`, `currency_code`, periodo, reparto y referencia. Contrato probado con productor → despachador → consumidor reales. | `TestHR04PayrollEnvelope`, `test_real_payload_reaches_the_ledger_once…` |
| HR-05 | P1 | Cerrado | `translate_cash_shift_event`: turno de `entity_id`, hora del evento (nunca del reloj del consumidor), persona = `cashier_user_id`; sin datos → se rechaza. Clave de marcación derivada del evento. | `test_canonical_cash_envelope_registers_the_cashier`, `test_envelope_without_time…` |
| HR-06 | P1 | Cerrado | Resolver identidad, registrar y marcar procesado en UNA transacción, sólo si el registro tuvo éxito; errores recuperables → `hr_inbox`; `LinkEmployeeUserUseCase` reprocesa. | `test_unlinked_cashier_is_held_and_applied_after_linking` |
| HR-07 | P1 | Cerrado | Política declarada por modalidad (ver decisiones); pendientes bloquean autorizar. | `test_one_complete_workday…`, `test_incident_only_period…` |
| HR-08 | P1 | Cerrado | Ausencias aprobadas entran como días pagables por tipo. Comisiones/préstamos: sin fuente canónica (abierto). | `test_approved_unpaid_leave_is_deducted` |
| HR-09 | P1 | Cerrado | Elegibilidad por vigencia (alta/baja); `employee_salary_history` con vigencia; tarifa del día. | `test_future_hire…`, `test_later_termination…`, `test_salary_change…` |
| HR-10 | P0 | Cerrado | `payroll_coverage` con `UNIQUE(employee_id, coverage_date)`: segunda ordinaria solapada → `PAYROLL_OVERLAP`; cancelar libera; huella → `IDEMPOTENCY_CONFLICT`. **Abierto:** corridas complementarias. | `TestHR10…`, `test_sqlite_coverage_key_is_structural` |
| HR-11 | P1 | Cerrado | Neto individual negativo bloquea autorizar y pagar; `payroll_payment_allocations` por empleado (suma = pago = asiento). | `test_negative_individual_net…`, `test_payment_requires_method…` |
| HR-12 | P1 | Cerrado | Tarifa por minuto en Decimal, un redondeo por línea: 56.25. | `test_overtime_rate_is_rounded_once` |
| HR-13 | P1 | Cerrado | Salida ligada a la jornada abierta (ventana 20 h). | `test_night_shift_is_one_workday` |
| HR-14 | P1 | Cerrado | Segmentos emparejados; salida extra = incidencia sin horas. | `test_split_segments…` |
| HR-15 | P1 | Cerrado | Descanso no pagado coherente en esperado y trabajado. | `test_unpaid_break…` |
| HR-16 | P1 | Cerrado | Se guarda `scheduled_shift_id`; resolvedor único; asignaciones solapadas se rechazan. | `test_resolved_shift_is_kept…` |
| HR-17 | P1 | Cerrado | Ajustes aprobados = capa efectiva reaplicada en cada recálculo, en la misma transacción; sólo entrada/salida, hora coherente y dentro de la jornada; ADJUSTED cuenta como presente. | `test_approved_adjustment…`, `test_adjustment_rejects…` |
| HR-18 | P1 | Cerrado (sin ledger) | Saldo por ciclo explicado (derecho, tomadas, reservadas). **Abierto:** ledger con arrastre/expiración. | `test_previous_cycle_consumption…` |
| HR-19 | P1 | Cerrado | Sin autoaprobación salvo `RRHH.permiso.autoaprobar`; pendiente la cancela quien pidió o quien aprueba; aprobada exige `RRHH.permiso.cancelar_aprobado` + motivo, publica `LEAVE_CANCELLED` y documenta nómina ya autorizada/pagada. | `test_self_approval…`, `test_cancelling_an_approved_leave…` |
| HR-20 | P1 | Cerrado | Alta con la sucursal de la sesión; diálogos ejecutan desde Aceptar y conservan la captura ante rechazo. | `test_ui_create_employee_uses_session_branch` + captura sobre copia real |
| HR-21 | P1 | Cerrado | Opciones de turno desde las filas del servicio. | `test_shift_options_build_from_rows` |
| HR-22 | P1 | Cerrado | Ver decisiones; la UI muestra horas locales. | `test_manual_local_time…`, `test_work_date_uses_branch_timezone` |
| HR-23 | P1 | Cerrado | `Employee.update_profile`/`change_salary` con invariantes del alta; bitácora antes/después (enmascara RFC/cuenta). | `test_update_enforces_creation_invariants…` |
| HR-24 | P1 | Cerrado | KPI: en turno, terminadas, faltas contra turno, ausencias autorizadas; mismo alcance en todos; "hoy" de la sucursal. | `test_dashboard_open_entry…` |
| HR-25 | P2 | Cerrado | Sumas Decimal; totales de varias corridas en una lectura (sin N+1). | `test_payroll_totals_are_exact_decimals` |
| HR-26 | P1 | Cerrado | `HRUnitOfWork` anidable: sólo la más externa confirma. | `test_outer_rollback_undoes_nested_use_case` |
| HR-27 | P2 | Cerrado | Autorizada = congelada; pagar exige el importe autorizado exacto. | `test_authorized_amount_is_frozen` |
| HR-28 | P2 | Cerrado | Empleados con búsqueda y paginación con total; selectores por búsqueda (`EmployeeSearchBox`). | `test_employee_101_is_reachable…` |
| HR-29 | P1 | Cerrado | Detalle por empleado y conceptos; diálogo de pago con método, referencia y confirmación; estado de contabilización visible; efectivo → caja. | `test_hr_payroll_contract.py` + capturas |
| HR-30 | P2 | Parcial | Editar expediente (organización, RFC, banco, emergencia, salario con vigencia), vincular usuario, solicitar ajuste desde la jornada, cancelar ausencia, listado de catálogos; Evaluaciones dice «No disponible». **Abierto:** edición de catálogos, historial en pantalla. | UI |
| HR-31 | P2 | Parcial | Las políticas de secuencia ahora sí corren en la ruta real; búsqueda de empleados única en RR. HH. **Abierto:** los casos de uso siguen instanciando `HRUnitOfWork` concreto; el `EmployeeQueryService` genérico de `backend/application/queries/` sigue existiendo. | — |

## CI

- `test_modulos_rrhh_is_a_thin_wrapper` (fallaba: el wrapper ya no existe) se
  redirigió a la composición viva: `test_live_hr_composition_wires_session_authorization`.
- `tests/test_rrhh_phase8_cleanup.py` sigue sin poder recopilarse (importa
  `core.services.driver_service`, eliminado); no se tocó.

## Segunda vuelta (2026-10-14): pendientes cerrados, recibo y checador

Migración **337**. Pruebas: `tests/integration/hr/test_hr_pending_features.py` (18) y
`test_loan_grant_installment_and_payment_reversal_are_posted` en el contrato con Finanzas.

| Pendiente | Qué se construyó |
|---|---|
| Recibo de nómina | `PayrollReceiptService` arma el recibo de cada empleado con lo GUARDADO (líneas, pago, referencia). **PDF** carta (reportlab), una hoja por empleado, firma de conformidad y aviso de que no es CFDI. **Ticket ESC/POS** a 32/48 columnas, enviado por la impresora que Document Output asigna al nuevo tipo **«Recibo de nómina»** (Configuración → Dispositivos), la misma vía que los cortes de Caja. Corrida no pagada = PRELIMINAR; segunda emisión = REIMPRESIÓN (bitácora). Desde Nómina: «Recibos PDF», «Imprimir recibos» y, en el detalle, por empleado. Permiso `RRHH.nomina.recibo`. |
| Checador | Arquitectura para cualquier lector: `TimeClockDevice` (aparato por sucursal), `EmployeeCredential` (número de usuario del checador, tarjeta, QR o PIN con hash; **nunca plantillas biométricas**), `hr_device_events` (evidencia, idempotente por aparato + id de evento) y una sola ruta de ingesta hacia la marcación canónica (zona, nocturno, segmentos e incidencias incluidos). Controladores: **kiosco** con lector USB tipo teclado (pantalla «Modo checador», evita doble lectura en 60 s), **archivo exportado** (attlog de ZKTeco o CSV), y **ZKTeco por red** (`pyzk`, opcional). Lo que llega sin credencial queda «sin empleado» y se aplica al dar de alta la credencial. Para otro fabricante basta un controlador nuevo en `TIME_CLOCK_DRIVERS`. Permisos `RRHH.checador.gestionar` / `.registrar`. |
| Complementaria | `GenerateComplementaryPayrollRunUseCase`: recalcula el periodo de una corrida ordinaria PAGADA y paga sólo la diferencia a favor (concepto Ajuste), con motivo y referencia; lo pagado de más se informa, no se descuenta solo. |
| Reverso de pago | `ReversePayrollPaymentUseCase`: corrida → cancelada con traza; libera días, conceptos y abonos; Finanzas revierte el asiento (`PAYROLL_PAYMENT_REVERSED`) o, si nunca se contabilizó, el `PAYROLL_PAID` se anula en la cola. |
| Bonos, comisiones, ajustes | Captura con motivo y fecha; aprueba OTRA persona; la ordinaria que cubre la fecha los toma; cancelarla los devuelve. Comisión automática desde Ventas: sigue abierta (no hay motor). |
| Préstamos y anticipos | Entrega: `EMPLOYEE_LOAN_GRANTED` → Dr 1145 «Préstamos y anticipos a empleados» / Cr Caja o Bancos. Cada nómina descuenta el abono sin pasar del saldo ni dejar neto negativo; el abono acredita 1145 (no «retenciones»). Al liquidarse queda pagado. |
| Libro de vacaciones | `leave_balance_movements`: abono por ciclo, reserva, consumo, liberación, vencimiento (6 meses tras el ciclo, regla declarada) y ajuste con motivo; consumo FIFO del ciclo vigente más antiguo. Las solicitudes previas se pasan al libro en la 337. |
| Motor fiscal | Puerto `PayrollWithholdingProvider` (ISR/IMSS como deducciones). Por omisión NO retiene (como hoy): las tablas oficiales y el CFDI requieren decisión fiscal y PAC. |
| HR-30 / HR-31 | Edición/desactivación de departamentos y puestos; se eliminó el `EmployeeQueryService` genérico sin llamadores. |

## Abierto, con motivo

- **Motor fiscal real** (ISR art. 96, subsidio, cuotas IMSS) y **CFDI de nómina** (PAC): necesitan tablas oficiales vigentes y decisión del contador.
- **Comisión automática** desde Ventas por vendedor (no existe la regla de comisión).
- Instrucción bancaria/conciliación del pago de nómina (hoy: pago registrado con referencia).
- Puertos de UoW (HR-31): los casos de uso siguen usando `HRUnitOfWork` concreto.
- Avisos (WhatsApp) de RR. HH.: el microservicio aún no está conectado al webhook en vivo.
- Envío de plantillas/usuarios AL checador de red (alta remota): hoy se enrola en el aparato y aquí se registra su número.

## Validación

- Selección del auditor + Caja + contrato con Finanzas: **368 aprobadas**.
- Regresión amplia (RR. HH., Caja, Finanzas, arranque, shell, seguridad, UI,
  arquitectura de permisos, e2e): 2135 aprobadas. La única falla causada por
  este trabajo (`test_without_finance_subscriber_the_z_cut_stays_pending`, que
  fijaba que `CASH_SHIFT_OPENED` saliera sin consumidor) se actualizó al contrato
  nuevo. Las demás son previas y ajenas: imports de `core` eliminado, conteos de
  permisos sembrados de Caja (`test_seeded_roles_resolve…`), `nav.losses`,
  PageStack/PageViewport/Productos/Precios (trabajo de otra persona sin commit).
- UI verificada con capturas sobre copia de la base real: alta con la sucursal
  de la sesión, asistencia en hora local, detalle por empleado y diálogo de pago.
- Segunda vuelta: RR. HH. + Finanzas + arquitectura de Finanzas y trinquete de
  cableado: **364 aprobadas**. En la regresión amplia (3250 aprobadas) aparecieron
  dos fallas propias y se corrigieron: los manejadores nuevos resolvían cuentas por
  código (ahora por el perfil `EMPLOYEE_LOAN`) y `PayrollPaidHandler` debía salir
  de la lista de manejadores sin consumidor. El resto de fallas de
  `tests/architecture` completo son previas y de otros módulos (Delivery,
  Configuración, Inventario, CRM, POS).
- Verificado sobre copia de la base real: empleado → bono aprobado por otra
  persona → nómina → pago por transferencia → recibo PDF (ver captura del
  recibo); ticket sin ruta asignada responde con el mensaje de configurarla;
  checador de kiosco con tarjeta registra la entrada; Finanzas agrega la cuenta
  1145 y el perfil `EMPLOYEE_LOAN` al arrancar.
