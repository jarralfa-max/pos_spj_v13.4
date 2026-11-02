# SDLC-WA-006 — Trabajadores del microservicio WhatsApp nunca corren y el webhook responde 200 aunque falle

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`InboxWorker.run_once` y `OutboundDispatcher.run_once` se registran pero nadie los llama: los mensajes salientes fallidos nunca se reintentan. `ReminderEngine` nunca se instancia. El webhook procesa en línea, se traga errores y devuelve 200, así que los mensajes fallidos se pierden.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `whatsapp_service/bootstrap/composition_root.py:218,243`
- `whatsapp_service/main.py:84-170`
- `whatsapp_service/flows/base_flow.py:15`
- `whatsapp_service/webhook/whatsapp.py:134-141`

## Impacto
Mensajes de clientes perdidos; recordatorios nunca enviados.

## Objetivo
- Los trabajadores corren con el ciclo de vida del servicio.
- Un mensaje que falla queda en la bandeja reintentable.
- Recordatorios activos o retirados explícitamente.

## Alcance
- **Incluye:** Arranque del microservicio y webhook.
- **No incluye:** Cutover a WA-1..20.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Microservicio WhatsApp: preservar los 3 shims de CLAUDE.md regla 9; el cutover del webhook a WA-1..20 sigue diferido por decisión del usuario.

## Trabajo previo relacionado
WA-17/WA-22.

## Preguntas abiertas
- Ninguna por ahora.

## Ampliación 2026-11-01 (`/sdlc-plan arquitectura docs/sdlc/inputs/whatsapp.md`)
Origen: `docs/sdlc/inputs/whatsapp.md` §17, §19, §20; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`.
- Solo se procesa `entry[0].changes[0].messages[0]` de cada lote (`whatsapp_service/models/message.py:52-63`, *verificado directamente*).
- El dedupe marca el mensaje como visto antes de procesarlo, no es atómico y se ignora el resultado de `log_message` (`whatsapp_service/state/conversation.py:118-135`; `webhook/whatsapp.py:114-139`): una excepción responde 200 y el reintento de Meta se descarta.
- Los webhooks de estado (sent/delivered/read/failed) se descartan sin persistir (`webhook/whatsapp.py:98-103`, *verificado directamente*); lo cortado por el limitador se descarta sin registro (`:120-122`).
- El corte al pipeline canónico es SDLC-WA-019; reintentos y dead letter, SDLC-WA-039.
