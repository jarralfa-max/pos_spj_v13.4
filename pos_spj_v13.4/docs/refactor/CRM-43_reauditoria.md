# CRM-43 — Re-auditoría de Clientes y CRM sobre la base real

Fecha: 2026-10-08/09. Disparador: re-pegado del «PROMPT MAESTRO DEFINITIVO» de
Clientes y CRM. CRM-0..42 ya existían (`CRM-*.md`): esto NO es una reconstrucción
sino una re-auditoría con la app viva, siguiendo el método de CASH-26 / LOY-29.

## Método

1. Copia de `data/spj_pos_database.db` → `run_database_bootstrap_sequence` (la misma
   conexión que la shell recibe al arrancar).
2. Se abrió Clientes y CRM por la ruta REAL (`CustomersCrmModuleActivator`) con el
   dueño real y con usuarios simulados de cada rol real (`gerente`, `cajero`,
   `solo_lectura`, `almacen`, `repartidor`), y se capturaron las 62 rutas a 1366×768.
3. Cada flujo se recorrió por los diálogos reales (el arnés contesta los formularios),
   no llamando a los casos de uso por fuera.

Línea base de pruebas de Clientes/CRM: **951 verdes, 4 rojas, 3 sin poder recolectarse**
— y aun así el CRM no se podía usar.

## Hallazgos (medidos en la base real)

| # | Sev. | Hallazgo | Estado |
|---|------|----------|--------|
| 1 | P0 | Sólo el dueño entraba al módulo. Los roles traían los códigos gruesos del módulo viejo (`CLIENTES.ver/crear/...`); el módulo exige `CLIENTES.acceso` y códigos granulares, y la entrada del menú (`CLIENTES_CRM.ver`) no la tenía ningún rol. Gerente, cajero y solo_lectura veían «No tienes permiso». | Cerrado — migr. 314 |
| 2 | P0 | El POS busca clientes con `CLIENTES.buscar`, que el cajero no tenía: **un cajero no podía ponerle cliente a una venta**. | Cerrado — migr. 314 |
| 3 | P0 | **53 de 62 rutas eran «sección en construcción»** y **130 de 141 casos de uso no tenían ninguna pantalla**: no se podía crear un prospecto, una oportunidad, un caso, una actividad, una solicitud de crédito, un consentimiento… | Cerrado — 62/62 rutas reales |
| 4 | P0 | La venta a crédito exigía `CLIENTES.credito.ver` y ningún cajero lo tiene: **ningún cajero podía vender a crédito**. Además el POS nunca enviaba `is_public_customer`: un «Público en general» podía recibir crédito. | Cerrado — verifica con `CLIENTES.elegibilidad_comercial.verificar`; tipo y estatus se leen del maestro |
| 5 | P1 | Alcance de datos de CRM sólo OWN/TEAM y el equipo nunca se arma: hasta el dueño veía únicamente lo asignado a sí mismo y **un prospecto recién creado (sin asignar) no aparecía en NINGÚN directorio**. | Cerrado — ejes BRANCH/COMPANY + «lo que creé sin responsable» |
| 6 | P1 | La proyección Ventas → Clientes (número de compras, última compra, etapa) se cableaba en `core/events`, ya borrado: la venta completada con cliente de la base real dejaba el expediente en 0 compras. | Cerrado — `customers/integrations/sales_wiring.py` + migr. 316 |
| 7 | P1 | `service_level_policies` vacía: ningún caso tenía vencimiento, «Casos fuera de SLA» siempre 0 y el escalamiento por SLA nunca podía dispararse. | Cerrado — migr. 315 |
| 8 | P1 | El directorio de clientes, con alcance de empresa, sólo listaba ACTIVOS: un cliente suspendido o bloqueado **desaparecía** y no había desde dónde reactivarlo (el filtro «Bloqueado» nunca mostraba nada). | Cerrado — `list_all` |
| 9 | P1 | Los mensajes de la venta a crédito no eran los de §39 («no elegible» a secas). | Cerrado — «Crédito insuficiente: disponible $X, requerido $Y.» y demás literales |
| 10 | P1 | El pipeline era dato pero no había forma de configurarlo (la entidad lo dejaba «para la fase de la pantalla»). | Cerrado — 4 casos de uso + `CRM.pipeline.configurar` |
| 11 | P2 | La UI mostraba códigos crudos (`PUBLIC_CUSTOMER`, `NOT_CONFIGURED`, `AL_CORRIENTE`). | Cerrado — `labels.py` |
| 12 | P2 | Datos sensibles sin enmascarar en el expediente (§75). | Cerrado — `customer_display_profile.py` |
| 13 | P2 | La búsqueda de clientes no buscaba por código aunque el campo lo decía. | Cerrado |
| 14 | P2 | 3 archivos de pruebas no recolectables (importaban `core/`, `application/`, `modulos/`, `api/routers` borrados); 2 pruebas de crédito del POS ídem; dobles de prueba sin el contrato actual. | Retirados / actualizados |
| 15 | P2 | La raíz de composición vivía en la UI y llamaba `.execute(connection, …)` (la guarda «UI sin SQL» lo marcaba). | Movida a `backend/infrastructure/desktop/customers_crm_factory.py` |

Hallazgos de mi propio trabajo durante la verificación (también cerrados): `presenter.run(name, …)`
chocaba con casos de uso que reciben un campo `name` («Nueva oportunidad» fallaba); los
formularios enviaban la fecha como texto y el caso de uso espera `date` (la conversión de
un prospecto ya hecha dejaba el formulario abierto: un reintento la habría duplicado); la
hora local sin zona contra el dominio en UTC habría marcado actividades vencidas horas antes;
la barra de 12 pestañas del expediente desbordaba a 1366 px.

## Decisiones del usuario (2026-10-08)

* **Matriz completa de roles.** Dueño/admin: todo. Gerente: supervisor comercial +
  supervisor de atención + gerente de crédito (aprueba límites, nunca su propia solicitud),
  ve su sucursal; sin configuración del módulo, anonimización ni exportación sensible.
  Cajero: busca, da de alta y edita datos básicos, contactos, direcciones, datos fiscales,
  consentimientos y preferencias, registra quejas/casos (ve los suyos), notas y
  seguimientos. Solo lectura: consulta sin datos sensibles. Almacén y repartidor: nada.
* **Construir todo por bloques**, verificado con capturas sobre la copia de la base real.
* **SLA estándar**: Baja 8 h/72 h, Normal 4 h/48 h, Alta 1 h/24 h, Urgente y Crítica
  30 min/8 h (primera respuesta/resolución), editables.
* **Clientes globales** para todos los roles; prospectos/oportunidades/casos: gerente su
  sucursal, cajero los suyos.

## Migraciones

| # | Qué hace |
|---|----------|
| 314 | Acciones de Clientes/CRM por rol (foto fija contrastada con el catálogo vivo) + `CLIENTES_CRM.ver`; borra `CLIENTES.eliminar` (no existe en el catálogo). |
| 315 | Cinco políticas de SLA por prioridad; no pisa una política genérica que ya exista. |
| 316 | Aplica una vez los `SALE_COMPLETED`/`SALE_REVERSED` ya despachados a la proyección de compras (idempotente por `event_id`). |
| 317 | `crm_reminders.delivered_at`: marca de entrega de los recordatorios (2026-10-09, cierre de pendientes). |
| 318 | Cotizaciones: `quotes`, `quote_lines`, `quote_audit_log`, `quote_outbox`; copia lo que hubiera en la tabla legacy `cotizaciones` (idempotente). |
| 319 | Permisos `COTIZACIONES.*` por rol (decisión del usuario, «como el CRM»); retira el grueso `eliminar`. |
| 320 | `DELIVERY.pedido.crear` a gerente y cajero: sin él Pedidos rechazaba la conversión de la cotización. |

## Qué se construyó

**UI (62/62 rutas reales).** Base común `CrmWorkbenchPage` (encabezado, KPIs, filtros,
tabla, detalle, acciones que se habilitan por estado Y permiso, aviso en línea);
formulario declarativo `CrmFormDialog` (campos canónicos, obligatorios, UTC, `date`,
`Decimal`; un rechazo no cierra el formulario; un éxito parcial no invita a duplicar);
`labels.py` y `formatting.py`. Páginas: prospectos (directorio, calificación con modelos
manual/puntaje/criterios/regla, conversión con o sin oportunidad, descartados, detalle);
oportunidades (directorio con ponderado/próxima actividad/días sin movimiento, pipeline
Kanban + tabla + resumen — arrastrar sólo ABRE el formulario de cambio de etapa —,
pronóstico, perdidas, detalle con historial de etapas y productos de interés);
actividades (agenda, tareas, llamadas, reuniones, visitas, seguimientos, notas,
recordatorios); atención (casos, quejas, solicitudes, incidencias, escalados, SLA con
políticas, detalle con escalamientos y resolución); crédito (solicitudes, perfiles,
exposición, CxC, historial, alertas); segmentación (segmentos, etiquetas, territorios,
carteras, responsables con historial); comunicaciones (consentimientos con evidencia,
preferencias, WhatsApp, avisos); privacidad (solicitudes ARCO, retención, anonimización,
exportaciones CSV auditadas); control (calidad de datos, duplicados y fusión, importación
CSV con mapeo y vista previa, auditoría unificada, configuración de pipeline y
automatizaciones); relación comercial (compras, pagos, pedidos, cotizaciones,
devoluciones, productos frecuentes). Expediente renovado: secciones editables, estado del
cliente (activar/suspender/bloquear/dar de baja/cerrar con motivo), altas en contexto.
Tablero con 6 KPI principales, 6 secundarios y las gráficas de §82.

**Backend nuevo** (sólo lo que faltaba): `CRMReferenceQueryService`,
`stage_definition_use_cases` (4), `account_use_cases` (2),
`DeactivateServiceLevelPolicyUseCase`, `DeactivateDataRetentionPolicyUseCase`,
`ExportCustomerDataUseCase`, `CustomerDirectoryQueryService`,
`customer_display_profile` (enmascarado), `SegmentationAdminQueryService`,
`PrivacyAdminQueryService`, `ControlQueryService`, `AuditTrailQueryService`,
`AutomationQueryService`, `CRMInsightsQueryService`, `CustomerHistoryQueryService.get_*`
(§28), `OpportunityDirectoryQueryService.list_rows`, `ServiceCaseQueryService.list_rows/
get_detail`, `CustomerCreditQueryService.list_rows/history`, `SLAInstance.first_response_status`,
`Opportunity.weighted_value`, `sales_wiring.py`.

## Verificación

* Copia de la base real, por rol: alta de prospecto → duplicado rechazado → contactado →
  calificado (criterios) → convertido con oportunidad → movido en el Kanban → llamada
  programada y completada → ganada; queja registrada por el cajero (ve sólo la suya) →
  el gerente la asigna, atiende, responde, escala, resuelve y cierra; crédito solicitado
  por el dueño, revisado y aprobado por el gerente, que NO puede aprobar el suyo; POS:
  $500 elegible, $7,000 «Crédito insuficiente…»; consentimiento con evidencia,
  preferencias, solicitud ARCO, anonimización rechazada si la autoriza quien la registró;
  importación CSV (1 creado, 1 duplicado, 1 error), calidad, auditoría, etapa nueva y una
  automatización que crea la tarea al registrar un prospecto; la venta completada real
  aparece en el expediente.
* Barrido de las 62 rutas: 0 placeholders, 0 errores de carga (dueño y gerente 62,
  solo_lectura 47, cajero 32).
* Pruebas: suite de Clientes/CRM **1035 verdes, 0 rojas**. Nuevas:
  `tests/integration/crm43/` (roles y siembras, flujos con el presentador real, UI real
  por rol) y `tests/unit/test_crm43_ui_components.py`; reescrita
  `tests/unit/test_customers_crm_directory_pages.py`.

## Cierre de pendientes (2026-10-09)

Hallazgo previo, medido en la base real: **ningún aviso llegaba a nadie**. La campana
de la barra superior (`NotificationDrawer`, SHELL-11) no tenía fuente; los
recordatorios del CRM se guardaban en `crm_reminders` y nadie los leía; el supervisor
de servicios de fondo (SHELL-14) existía sin un solo servicio.

| Pendiente | Cierre |
|-----------|--------|
| Disparadores por tiempo sin programador | Los siete (`LEAD_IDLE`, `OPPORTUNITY_IDLE`, `OPPORTUNITY_OVERDUE`, `CUSTOMER_INACTIVE`, `SLA_AT_RISK`, `SLA_BREACHED`, `CREDIT_REVIEW_DUE`) en `EvaluateTimeBasedAutomationTriggersUseCase` con consultas propias (`AutomationSweepRepository`). Se disparan **una vez por registro y ancla** (último movimiento, última compra, fecha de cierre, revisión de crédito, SLA): pasadas repetidas no duplican; el registro vuelve a ser elegible cuando su ancla cambia. Los corre `run_crm_background_cycle` al iniciar sesión y cada 5 min (`PeriodicTaskService` bajo el supervisor, en `desktop_shell_window_composition.py`). |
| `SEND_NOTIFICATION` | Aviso real en la bandeja personal (`notification_inbox`) a una persona fija y/o al responsable del registro, con el nombre del registro y el texto de la regla; idempotente por `dedupe_key`. |
| `CHANGE_PRIORITY` | Prospectos (`Lead.change_priority` + `UpdateLeadUseCase(priority=)`, también editable desde «Editar prospecto») y casos (`UpdateServiceCaseUseCase`), cada uno con su permiso de edición. |
| Reglas imposibles | El dominio rechaza al guardar una acción que no aplica al registro del disparador, un umbral sin días o una acción sin sus datos (antes se guardaban y dejaban ejecuciones OMITIDAS para siempre). El formulario ofrece las siete acciones. |
| Llave de idempotencia compartida | Dos reglas del mismo disparador usaban la misma llave (`op-task`) y la segunda recibía la tarea de la primera; ahora cada regla y cada registro tienen la suya. |
| Recordatorios | `DispatchDueCRMRemindersUseCase` entrega los vencidos a la campana (migr. 317). El diálogo sólo ofrece «En la aplicación»: correo y WhatsApp interno no tienen remitente. |
| Campana | `NotificationInboxFeed` la llena con los avisos del usuario de la sesión (recordatorios, automatizaciones, alertas de productos y entregas) cada minuto; abrir un aviso lo marca leído en la base (sólo el destinatario puede). |
| Alcance por registro | `CRMRecordScopeGuard` en la raíz de composición: antes de operar un prospecto, oportunidad o caso (o una actividad/tarea/nota sobre ellos) el registro debe caer en el alcance con que el actor lo vería en su bandeja. Error `OUT_OF_SCOPE` con motivo en español. |
| Dependencias de pruebas | `bcrypt`, `argon2-cffi` y `httpx` instalados en el venv (ya listados en `requirements.txt`). |

Verificado sobre la copia de la base real (`live_bg.py`): migración 317 aplicada; regla
«cliente inactivo → escalar caso» rechazada («no aplica a clientes»); con la ventana
viva, el ciclo entregó el aviso del prospecto frío y el recordatorio vencido, la campana
mostró 2 sin leer, y una segunda pasada no repitió nada. Pruebas nuevas:
`tests/integration/crm43/test_crm43_automation_background.py` (16),
`tests/ui/shell/test_notification_inbox_feed.py` (4), validación de reglas en
`tests/unit/crm/test_automation_rule_entity.py`, formulario en
`test_crm43_ui_real_presenter.py` y supervisor en
`tests/integration/shell/test_desktop_shell_window_composition.py`. Suite de
Clientes/CRM + campana: **1311 verdes**; la única roja es la guarda de valores fijos por
`hr/dialogs/hr_dialogs.py` (ajeno a este trabajo).

## Cotizaciones (2026-10-09, «construyelo»)

Medido antes: no existía. Los casos de uso `create_quote_use_case.py` y afines eran
cascarones `DelegatingUseCase` sin manejador ni llamadores; la tabla legacy
`cotizaciones` no tenía escritor (0 filas). Pedidos ya preveía la conversión (tipo
`QUOTE_CONVERTED`, campo `customer_orders.quote_id`) sin productor.

**Decisiones del usuario (2026-10-09):** aceptada → **Pedido** a precios cotizados;
**precio bajo lista → la aprueba otra persona** (nunca quien la hizo; a lista no se
aprueba; sin porcentajes inventados); **roles como el CRM** (dueño/admin todo; gerente su
sucursal, aprueba y convierte; cajero las suyas, sin aprobar; solo lectura consulta);
**vive dentro de Clientes y CRM**.

| Pieza | Dónde |
|-------|-------|
| Dominio | `backend/domain/quotes/` — `Quote`/`QuoteLine`, ciclo Borrador → Por aprobar/Aprobada → Enviada → Aceptada → Convertida; Rechazada, Vencida, Cancelada; nueva versión (`COT-000001/2`) |
| Precio | `backend/application/quotes/pricing.py` — catálogo de la sucursal (misma regla que Pedidos) + `PricingReadFacade.sale_price` con cliente, cantidad y canal `SALES_REP`; lista y mínimo |
| Casos de uso | `quote_use_cases.py` (alta, partidas, terminar, aprobar, regresar, enviar, aceptar, rechazar, cancelar, nueva versión, vencer), `convert_quote_use_case.py` (Pedido `QUOTE_CONVERTED`, idempotente por folio), `export_quote_use_case.py` (PDF sólo de aprobada en adelante) |
| Consultas | `QuoteQueryService` con alcance propias/sucursal/empresa |
| UI | `pages/quote_pages.py`: Cotizaciones, Por aprobar, Detalle (partidas, importes, historial); «Cotizar» desde la oportunidad y sus cotizaciones en su detalle; historial del cliente lee la tabla canónica |
| Fondo | el ciclo del CRM vence las cotizaciones cuya vigencia pasó |
| Menú | una sola entrada: la sección «Cotizaciones». La ruta `customers.quote_history` de «Relación comercial» se retiró por duplicada; lo de un cliente queda en la pestaña de su expediente |
| Pedidos | `CreateCustomerOrderUseCase(quote_id=…)` |

Verificado sobre la copia de la base real: el cajero cotizó a «Restaurante La Fogata»
12.5 kg de Alas a $72 (lista $80) y 5 kg de Pechuga a lista → por aprobar ($1,575 a
lista, $100 de descuento, $1,475); el gerente la aprobó, generó el PDF (encabezado con
la empresa real), la marcó enviada y aceptada y la convirtió: pedido `QUOTE_CONVERTED`,
canal `SALES_REP`, en borrador, con los precios cotizados. Pruebas:
`tests/unit/quotes/` (16), `tests/integration/crm43/test_crm43_quotes.py` (15) y la del
detalle en `test_crm43_ui_real_presenter.py`.

## Menú sin duplicados (2026-10-09, observación del usuario)

El menú lateral repetía como «páginas» lo que ya son pestañas del expediente: elegías un
cliente y veías la misma sección. Se retiraron 12 entradas: Cotizaciones (historial, en
Relación comercial), Cuentas comerciales, Contactos, Direcciones, Datos fiscales,
Consentimientos, Preferencias, Compras, Pedidos, Devoluciones, Productos frecuentes y
Notificaciones (misma sección que WhatsApp). El grupo «Relación comercial» desaparece. Todo
sigue en el expediente con las mismas secciones y permisos. Menú: 53 entradas (dueño y
gerente), 37 (solo lectura), 22 (cajero).

## Pendiente / riesgos

* Gráficas: en el arnés sin QtWebEngine se dibujan como tabla de respaldo (componente
  canónico); con WebEngine son ECharts.
* **Pedidos sin matriz de permisos por rol** (hallazgo al convertir): en la base real
  ningún rol tiene códigos granulares `DELIVERY.*` (sólo los gruesos del sembrado base,
  que Pedidos no revisa); sólo dueño/admin operan Pedidos. La migración 320 concede
  únicamente `pedido.crear` a gerente y cajero para la conversión; quién ve, confirma,
  prepara y entrega pedidos es una decisión pendiente de Pedidos.
* Cotizaciones: no se envían por WhatsApp ni correo desde el sistema (no hay remitente
  conectado); «Marcar enviada» registra la entrega hecha por fuera con el PDF. Los
  cascarones legacy `backend/application/use_cases/*quote*` siguen sin llamadores (una
  prueba de andamiaje los fija).
* El ciclo del CRM corre en cada estación abierta; la deduplicación por ejecución
  evita repetir, pero dos estaciones en el mismo segundo podrían disparar la misma regla
  dos veces (riesgo bajo, sin servidor central todavía).
* Una ejecución FALLIDA de una regla por tiempo no se reintenta sola: queda en el
  historial de la regla hasta que el registro cambie.
