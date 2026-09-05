# WA-18 — Notificaciones (canal WhatsApp)

Ejecutado: 2026-09-02. §21-22 del prompt maestro. Cierra el batch
WA-13..WA-18 pedido en esta sesión.

## Qué se construyó

- `application/notification_service.py::NotificationService` — cubre las
  MISMAS 4 notificaciones de negocio que `router/notify_router.py`
  (legacy, sin tocar): pedido listo, anticipo requerido, cotización
  lista, mensaje libre. A diferencia del legacy (`send_text` directo,
  sin cola ni reintento), encola vía `OutboundMessageService` (WA-17) con
  un `operation_id` determinístico por tipo+folio+teléfono — un
  reintento del LLAMADOR (el ERP) para la MISMA notificación no duplica
  el mensaje en cola (`whatsapp_outbox.operation_id` es `UNIQUE`, WA-3).
- `infrastructure/webhooks/outbound_dispatcher.py::OutboundDispatcher.dispatch_now()`
  (nuevo método, agregado en esta fase) — despacha UN mensaje específico
  de inmediato tras encolarlo, para que el llamador síncrono reciba una
  señal real de éxito/fallo en la misma respuesta HTTP, no solo "quedó en
  cola" — la garantía de entrega eventual (`run_once()` periódico) sigue
  cubierta si el intento inmediato falla.
- `router/notify_dispatch_router.py` — mismas 4 rutas que el legacy, bajo
  `/api/notify/v2/*` (no `/api/notify/*`, para coexistir sin colisión).
  Misma autenticación (`middleware.service_auth.require_service_auth`,
  WA-1). Montado ADITIVAMENTE en `main.py` junto al legacy — ningún
  llamador real (`core/integrations/whatsapp_client.py`, lado ERP) fue
  migrado a esta ruta en esta fase; es la decisión de cutover pendiente
  para una fase posterior, mismo criterio que cada mecanismo nuevo desde
  WA-4.

CompositionRoot: +1 servicio (`notification_service`) — `REQUIRED_SERVICES`
pasó de 39 a 40.

## Hallazgo real encontrado en el smoke test — corregido en esta misma fase

El smoke test contra `main.py` mostró `/health` reportando
`outbox_worker`/`erp_api` como `UNKNOWN — "pendiente — WA-17"`/`"pendiente
— WA-9"` **a pesar de que ambas fases ya estaban construidas y reales**
(WA-9 desde el 2026-09-01, WA-17 en esta misma sesión) — `bootstrap/health_checks.py`
nunca se actualizó cuando esas fases cerraron. Corregido en el mismo pase
en que se encontró (mismo criterio que los "self-inflicted regressions"
de WA-10/11):

- `check_outbox_queue()` — mismo criterio que `check_inbox_queue` (WA-6),
  en sentido saliente: profundidad/antigüedad real de `whatsapp_outbox`.
- `check_erp_api()` — reporta `HEALTHY` si `CompositionRoot` resolvió un
  `ERPBridge` real (WA-9), `DEGRADED` si degradó a `UnavailableErpClient`
  (esquema legacy no disponible en la conexión).

Verificado con el smoke test: `/health` contra la BD bootstrapeada
completa ahora reporta `outbox_worker: HEALTHY` y `erp_api: HEALTHY`, no
`UNKNOWN` falso.

## Tests

108 tests nuevos: `test_notification_service.py` (11 — incluida la
deduplicación real de reintento del llamador), `test_notify_dispatch_router.py`
(5, end-to-end con auth HMAC real vía `TestClient`), 4 tests nuevos en
`test_outbound_dispatcher.py` (`dispatch_now`), 9 tests nuevos en
`test_health_checks.py` (`check_outbox_queue`/`check_erp_api`), accessor
de `CompositionRoot` (+1).

Suite completa: **675 passed, 11 failed** (mismos preexistentes desde
WA-1). Sintaxis global: sin errores. Smoke test real contra `main.py`
bootstrapeado desde cero: `/health` 200, las 8 rutas `/api/notify/*` +
`/api/notify/v2/*` coexistiendo, todos los servicios de WA-13..WA-18
resueltos como sus clases reales (no fallback) contra la BD completa.

## Estado del canal tras WA-1..WA-18

Seguridad, dominio, esquema, bootstrap, provider gateway, webhook/inbox,
conversation engine, intent resolution, ERP contracts, pedidos,
cotizaciones, pagos (WA-1..12) — más delivery, consentimiento, fidelidad,
handoff, outbox/despacho saliente y notificaciones (WA-13..18) — existen,
están probados (675 tests de esta iniciativa) y verificados contra un
arranque real de `main.py`. Todavía **nada de esto está conectado al
webhook en vivo** (`webhook/whatsapp.py` sigue procesando síncronamente
vía `MessageRouter`/flows/) — sigue siendo la pieza que falta para que
todo este trabajo deje de ser "nuevo en paralelo". Fuera de alcance de
este batch: WA-19 (UI), WA-20 (Observabilidad), WA-21 (eliminación de
legacy — sigue gated en la decisión de producto sobre el stack
ERP-embedded/Rasa, diferida por el usuario en WA-9), WA-22 (validación
final), y el cutover real de los llamadores ERP hacia las rutas `/v2`
nuevas (notificaciones) y hacia el pipeline conversacional nuevo en
general.
