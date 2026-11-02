# SDLC-WA-019 — Corte del webhook vivo al pipeline canónico: hoy procesa en línea con el router legacy y el stack nuevo no recibe tráfico

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §17, §20 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-002, SDLC-WA-006, SDLC-WA-016, SDLC-WA-048

## Problema
Existe un webhook canónico (`WebhookProcessor` → `whatsapp_inbox` → `InboxWorker`), pero el webhook vivo `/webhook` procesa síncrono con `MessageRouter` y `flows/`, espera a Ollama, a Graph y al ERP antes de responder, y no hay ruta `/webhooks/whatsapp`. Conviven dos webhooks, dos motores de conversación y dos resolvedores de intención; el CompositionRoot solo alimenta `/health`, `/diagnostics` y `/api/notify/v2` (sin llamadores). El propio procesador canónico dice "No reemplaza el webhook en vivo" y rechaza números no registrados, que hoy no se pueden registrar.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/webhook/whatsapp.py:33,63,134-141` *(verificado directamente)*
- `whatsapp_service/infrastructure/webhooks/webhook_processor.py:10-14,75-126,85-91`
- `whatsapp_service/infrastructure/webhooks/inbox_worker.py:11-14,32-36` — manejador por defecto no-op
- `whatsapp_service/bootstrap/composition_root.py:216-244`
- Pruebas: `whatsapp_service/tests/test_webhook_processor.py`, `test_inbox_worker.py` (unitarias, sin integración con el webhook vivo)

## Impacto
Todo lo construido en WA-1…20 (idempotencia, outbox, handoff, consentimiento canónico) no protege ni un mensaje real.

## Objetivo
- Un único webhook `GET/POST /webhooks/whatsapp`: valida, persiste en inbox, responde 200 rápido.
- El trabajador procesa con el motor canónico; el router legacy deja de recibir tráfico.
- Prueba de punta a punta: mensaje firmado → inbox → respuesta en outbox.

## Alcance
- **Incluye:** Ruta canónica, cableado del procesador y del trabajador, retiro del procesamiento en línea.
- **No incluye:** Reescribir cada flujo (SDLC-WA-022/023); borrar el legacy (SDLC-WA-050).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-6, WA-22 (memoria: "nada cableado al webhook vivo"); SDLC-WA-006.

## Preguntas abiertas
- El corte del webhook y la eliminación del legacy (WA-21) quedaron diferidos por decisión del responsable desde WA-9. ¿El documento `inputs/whatsapp.md` ("no conservar dos webhooks") levanta esa decisión?
- ¿Hay conversaciones reales en `conversations.db` que deban migrarse al corte, o se puede empezar limpio?
