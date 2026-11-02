# SDLC-WA-036 — El bot promete "Te comunico con un asesor" y nunca escala; el personal contesta desde su teléfono personal

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §47, §48 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-019

## Problema
El cliente recibe el mensaje de que lo comunican con un asesor, pero `HandoffService.escalar` nunca se llama y `HandoffCoordinator` no está conectado. Cuando se escala, al personal se le pide "Responde directamente al cliente desde WhatsApp": las respuestas humanas salen de teléfonos personales, fuera del sistema y sin rastro. Faltan agentes, colas, enrutamiento, SLA, motivos y estados de §47.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/messaging/interactive.py:174-179`; `router/message_router.py:186`
- `whatsapp_service/middleware/handoff.py:19,33`; `application/handoff_service.py:35,52-64,58`
- `whatsapp_service/domain/whatsapp/enums.py:274-280` — 4 estados
- `backend/infrastructure/db/schema/whatsapp_schema.py:327` — asignación a teléfono de personal
- Prueba: `whatsapp_service/tests/test_handoff_service.py` (canon)

## Impacto
Clientes que piden ayuda humana quedan sin respuesta; conversaciones con el negocio fuera de control y de auditoría.

## Objetivo
- Solicitud de handoff real con motivo, cola, asignación por política (sucursal, horario, carga) y SLA.
- La respuesta humana sale por el canal y queda registrada.

## Alcance
- **Incluye:** Backend de handoff, agentes, colas y SLA.
- **No incluye:** Pantalla de atención (SDLC-WA-041/042).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-16 (memoria: coordinador envía síncrono, nunca se pasó al outbox).

## Preguntas abiertas
- ¿Quién atiende conversaciones (roles), con qué horario y qué SLA de primera respuesta?
