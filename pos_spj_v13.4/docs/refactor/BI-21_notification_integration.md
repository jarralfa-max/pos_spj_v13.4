# BI-21 — Notification Integration (ERP + WhatsApp)

Estado: **DONE** (dominio + orquestación completos vía puertos; sin
adaptador de infraestructura real todavía — el research de esta fase
identificó exactamente qué debe envolver ese adaptador)

## Alcance

§51-55: las alertas de BI-20 deben llegar vía Notification Management, BI
nunca llama WhatsApp directo, destinatarios se resuelven por permiso/rol/
scope (§118), preferencias de suscripción por usuario (§55) deciden canal/
severidad mínima/horario de silencio.

## Investigación previa (resumen — informa el diseño de puertos)

Antes de escribir código se investigó el sistema de notificaciones **real**
ya existente en el repo, para que los puertos nuevos calcen con él en vez de
inventar una forma incompatible:

- **Dos capas coexisten**: `backend/domain/notifications/` (SET-20,
  catálogo/configuración de cuentas-plantillas-rutas) y
  `core/services/notifications/` (`RecipientResolver`,
  `NotificationDispatcher`, `NotificationPolicyService` — la orquestación de
  entrega real que ya usa el resto del ERP).
- `RecipientResolver.by_role(tipo, sucursal_id)` ya resuelve destinatarios
  por matriz rol→tipo de evento vía RBAC — **exactamente** el patrón "sin
  `if rol == '...'`" que pide §118. Es el adaptador natural detrás de
  `AlertRecipientResolverPort`.
- `NotificationDispatcher.dispatch_staff(tipo, destinatarios, titulo,
  mensaje, datos, sucursal_id)` ya separa resolución/política/despacho — el
  adaptador natural detrás de `AlertDispatchPort`.
- Toda ruta de WhatsApp pasa por un único `WhatsAppService.send_message()`
  — confirmado que ningún módulo lo llama directo, siempre a través de un
  dispatcher/adaptador.
- **No existía** ningún concepto de preferencias de suscripción para
  alertas de staff (quiet hours/severidad mínima/opt-in) — es vocabulario
  nuevo que BI-21 sí tuvo que inventar (`AnalyticalNotificationSubscription`),
  no hay nada previo que romper o duplicar.
- `NotificationChannel` (enum canónico, `backend/domain/notifications/enums.py`)
  ya existía con `WHATSAPP`/`SMS`/`EMAIL`/`PUSH` pero **sin `IN_APP`** — se
  amplió aditivamente (ver abajo) en vez de crear un enum paralelo.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/notifications/enums.py` (ampliado) | Se agregó `NotificationChannel.IN_APP` — canal por defecto para alertas internas, que el enum canónico no tenía. Cambio aditivo puro; se verificó que ningún consumidor itera exhaustivamente sobre los miembros del enum (los 41 tests de `tests/unit/notifications/` siguen verdes). |
| `backend/domain/analytical_alerting/value_objects/notification_subscription.py` | `AnalyticalNotificationSubscription` (§55: user_id, alert_type, minimum_severity, channel, branch_scope, quiet_hours, enabled). `ALL_BRANCHES` reutiliza el mismo sentinel que `DemandPlanningService` (BI-12) ya usa para "sin sucursal específica" — un solo vocabulario, no dos. |
| `backend/domain/analytical_alerting/services/notification_gating.py` | `severity_meets_minimum`, `is_within_quiet_hours` (maneja ventanas que cruzan medianoche), `should_notify()` — combina las 4 condiciones (habilitado, tipo de alerta coincide, severidad ≥ mínimo, scope de sucursal coincide, fuera de horario de silencio). Modelo **opt-in**: sin suscripción, sin notificación, aunque el destinatario sea un candidato válido. |
| `backend/domain/analytical_alerting/integration_ports.py` | `AlertRecipient` + `AlertRecipientResolverPort` + `AlertDispatchPort` — moldeados exactamente sobre `RecipientResolver`/`NotificationDispatcher` reales (arriba), no inventados desde cero. |
| `backend/application/analytical_alerting/services/alert_notification_service.py` | `AlertNotificationService.notify()` — resuelve candidatos vía el puerto, filtra por `should_notify()` usando las suscripciones del llamador, agrupa por canal, despacha vía el puerto. Nunca importa WhatsApp/dispatcher concretos. |
| `tests/architecture/test_analytical_alerting_never_imports_notification_infra_directly.py` | Guardrail — igual patrón que BI-14 (Treasury). Los needles usan forma de import (`"import RecipientResolver"`) en vez de subcadena de nombre de clase desnuda, porque el propio `AlertRecipientResolverPort` legítimamente contiene "RecipientResolver" en su nombre — un detalle que el primer intento de este guardrail no consideró y que el propio test atrapó al fallar sobre su propio archivo. |

## Auditoría REGLA CERO

`AnalyticalNotificationSubscription.id` validado con `validate_uuidv7()`.
N/A para el resto.

## Tests

`test_notification_subscription.py` (6), `test_notification_gating.py`
(11, incluye ventana de horario de silencio que cruza medianoche),
`test_alert_notification_service.py` (4, con fakes — agrupación por canal,
exclusión por severidad, cero candidatos suscritos ⇒ cero despachos) +
`tests/architecture/test_analytical_alerting_never_imports_notification_infra_directly.py`
(1). **22 tests nuevos, todos verdes** (más los 41 tests preexistentes de
`tests/unit/notifications/` reconfirmados verdes tras ampliar el enum).

## Pendiente

- Ningún adaptador de infraestructura real implementa
  `AlertRecipientResolverPort`/`AlertDispatchPort` todavía contra
  `RecipientResolver`/`NotificationDispatcher` reales — se construye cuando
  exista un caller de producción (`AnalyticalAlertEngine` de BI-20 no tiene
  ningún Use Case/scheduler que lo invoque con datos reales todavía).
- `NotificationDispatcher`/`RecipientResolver` **no están wireados en
  `core/app_container.py`** (hallazgo del research, no de esta fase) — un
  futuro adaptador tendría que construirlos él mismo (solo necesitan
  `db`/`whatsapp_svc`/`sucursal_id`, todos disponibles en el container).
- Sin persistencia de `AnalyticalNotificationSubscription` — vive en
  memoria, mismo criterio que `AnalyticalAlertRule`/`BusinessRecommendation`.
