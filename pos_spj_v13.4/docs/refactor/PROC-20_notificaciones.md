# PROC-20 — Notificaciones y WhatsApp: Procesamiento Cárnico

Estado: **DONE** (solicitud de alerta genérica vía puerto; sin entidad
persistida propia — la fila de la alerta la posee el microservicio de
notificaciones, Procesamiento solo pide y audita)

## Alcance y decisión de arquitectura

`whatsapp_service/` ya es un microservicio FastAPI independiente y completo
(`WA-0..20`, ver memoria `whatsapp_channel_enterprise_transformation`);
Procesamiento no le añade lógica de mensajería ni de plantillas — solo
necesita un punto de salida para pedirle una alerta, exactamente el mismo
boundary que PROC-15 (Mermas) y PROC-16 (Calidad) ya establecieron: nunca
llama directo al servicio externo, siempre a través de un puerto con
default `Null` que dice honestamente "integración pendiente".

`NOTIFICATIONS_MANAGE`/`WHATSAPP_ALERTS_MANAGE` (PROC-1, sección
"configuración") ya existían pero son permisos de **gestión** (configurar a
quién/cómo se notifica), no de **acción** (disparar una alerta ahora). Se
añadió `ALERT_SEND` para esa acción, separada — mismo criterio que separó
`YIELD_REVIEW`/`YIELD_APPROVE` de `REQUEST_LOSS_CASE`.

## Puerto nuevo: `NotificationPort`

`send_alert(*, operation_id, alert_type, severity, message, branch_id) ->
str | None` — `alert_type`/`severity` son `str` libres (no un enum
canónico): a diferencia de `ProcessType`/`OutputType`/etc., que son
vocabulario del dominio de Procesamiento, el conjunto de tipos de alerta lo
termina definiendo el lado de notificaciones (plantillas, destinatarios por
tipo), así que fijar un enum aquí sería adivinar un contrato que no nos
pertenece. `NullNotificationPort` devuelve `None`, igual que el resto de los
puertos Null.

## Caso de uso: `RequestProductionAlertUseCase`

No ancla en ninguna entidad existente — una alerta es un hecho libre
("rendimiento crítico", "equipo fuera de servicio", "incidencia abierta"),
así que genera su propio `alert_id` (UUIDv7 nuevo) solo para tener una
identidad distinta de `operation_id` que anclar en la auditoría
(`meat_processing_audit_log`, `entity_type="ProductionAlert"`) y en el
evento — `build_meat_processing_event` exige `entity_id != operation_id`.
Valida `severity` contra un conjunto fijo (`INFO`/`WARNING`/`CRITICAL`) antes
de tocar el puerto. Idempotente sobre el `operation_id` del llamador vía
`meat_processing_processed_events` (mismo mecanismo que
`RecordProcessOutputsUseCase`/`RequestLossCaseForYieldVarianceUseCase`) —
un reintento con el mismo `operation_id` nunca vuelve a llamar al puerto ni
duplica el evento.

## Evento nuevo

`PROCESSING_ALERT_REQUESTED` — el único evento de notificaciones que
`events.py` define; el catálogo completo de eventos de notificación del §60
(por tipo de destinatario, plantilla, etc.) no se modela aquí porque
Procesamiento no lo consume ni lo produce — eso vive del lado de
`whatsapp_service`.

## Tests

`tests/integration/meat_processing/test_meat_processing_notification_use_cases.py`
(4 tests): sin puerto → pendiente; con puerto falso → éxito + auditado +
evento en outbox; idempotencia sobre el mismo `operation_id` (el puerto no
se vuelve a llamar); severidad desconocida rechazada sin tocar el puerto.

## Pendiente

- `NotificationPort` real contra `whatsapp_service` — cuando se decida el
  mecanismo de invocación cross-servicio (REST síncrono o vía EventBus,
  igual que documenta `CLAUDE.md` §15 "Patrones de integración").
- Ningún caso de uso existente (`RecordProcessOutputsUseCase` cuando el
  rendimiento sale `CRITICAL`, `ReportProcessIncidentUseCase` para
  incidencias graves, `AssignEquipmentUseCase`/mantenimiento) dispara
  automáticamente `RequestProductionAlertUseCase` — es una acción explícita
  separada, a propósito (mismo criterio que PROC-15: nunca un efecto
  colateral silencioso dentro de otro caso de uso). Cablear disparadores
  automáticos, si se decide que hacen falta, es trabajo de una fase
  posterior con su propia decisión de diseño.
