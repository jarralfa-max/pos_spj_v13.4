# WA-20 — Observabilidad (canal WhatsApp)

Ejecutado: 2026-09-02. §58 del prompt maestro (mismo § que `/health`,
WA-4) — ver nota de alcance en `WA-19_ui.md` sobre la falta del texto
original detallado para esta fase.

## Qué se construyó

`/health` (WA-4, extendido en WA-5/6/17/18) responde una pregunta
binaria-ish: "¿está bien el sistema?" (HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN
por subsistema). No responde la pregunta que un operador hace DESPUÉS de
que `/health` ya dijo DEGRADED: "¿cuántas conversaciones hay ahora?
¿qué tan atrasada está la cola? ¿cuántos handoffs llevan abiertos?".
WA-20 es esa segunda pieza.

- `application/diagnostics_service.py::DiagnosticsService.get_metrics()`
  — agrega, sobre la MISMA conexión que el resto del `CompositionRoot`
  (sin BD de métricas separada): conversaciones por estado, mensajes
  hoy/total por dirección, backlog + antigüedad de inbox/outbox, dead
  letter (resueltos/no resueltos), handoff por estado + antigüedad del
  más viejo abierto, idempotencia por estado + tipo de operación, y
  drafts de pedidos/cotizaciones/entregas por estado.
- `router/diagnostics_router.py` — `GET /diagnostics`, protegido con
  `require_service_auth` (WA-1) — a diferencia de `/health` (público,
  consumido por `WhatsAppClient.health_check()` del lado ERP), este
  endpoint expone volumen operativo/de negocio real, así que no es
  público. Montado ADITIVAMENTE en `main.py`.

CompositionRoot: +1 servicio (`diagnostics_service`) — `REQUIRED_SERVICES`
pasó de 40 a 41.

## Reutiliza el mismo criterio de parseo de fechas que WA-19 corrigió

Todas las edades (`oldest_pending_age_seconds`, `oldest_open_age_seconds`)
se calculan parseando el string ISO almacenado con `datetime.fromisoformat()`
en Python y comparando objetos `datetime`, nunca comparando strings de
fecha en SQL — el mismo bug de formato (`T`+offset vs. espacio sin zona)
que WA-19 encontró y corrigió en `WhatsAppMetricsRepository` se evitó
aquí desde el diseño inicial, no como una corrección posterior.

## Tests

24 tests nuevos: `test_diagnostics_service.py` (14 — incluida
degradación sin tablas, conteos por estado/dirección, antigüedad de
colas), `test_diagnostics_router.py` (2, end-to-end con auth HMAC real),
accessor de `CompositionRoot` (+1).

Suite completa: **686 passed, 11 failed** (mismos preexistentes desde
WA-1). Smoke test real contra `main.py` bootstrapeado: `/diagnostics`
responde 200 con la forma completa de métricas contra la BD real.

## Hallazgo colateral: `erp_ports.py` corrupto en disco, corregido

Durante esta fase se encontró `whatsapp_service/domain/whatsapp/erp_ports.py`
con un prefijo literal `+456` insertado antes del comentario de la
primera línea — rompía la sintaxis del archivo y por lo tanto la
colección completa de la suite de tests (`SyntaxError: from __future__
imports must occur at the beginning of the file`). El archivo estaba
abierto en el editor del usuario en el momento; corregido de inmediato
(se quitó el prefijo, sin ningún otro cambio de contenido) antes de
continuar.

## Siguiente fase

WA-22 (Validación final) — WA-21 queda diferido por decisión explícita
del usuario (misma decisión de producto pendiente desde WA-9).
