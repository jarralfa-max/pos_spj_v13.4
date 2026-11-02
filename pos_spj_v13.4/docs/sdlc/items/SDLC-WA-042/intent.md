# SDLC-WA-042 — Sin composer ni respuesta humana desde el ERP, y el sistema de diseño no tiene componentes de conversación

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §68, §69 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-041, SDLC-WA-036

## Problema
No existe endpoint ni pantalla para responder: texto, plantilla, imagen, documento, ubicación, respuesta rápida, nota interna o handoff. El sistema de diseño no tiene ConversationList, ConversationThread, MessageComposer, AgentBadge ni SlaBadge. El único control antes de enviar es el de consentimiento, que falla abierto.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `frontend/desktop/components/` — solo `page_header`, `kpi_bar`, `status_badge`, `side_nav` relevantes
- `whatsapp_service/main.py:189-197` — sin router de respuesta
- Prueba: ninguna

## Impacto
Las respuestas humanas siguen fuera del sistema (ver SDLC-WA-036).

## Objetivo
- Composer que valida ventana de conversación, consentimiento, tipo de plantilla, permiso y número emisor, y envía por el outbox.
- Componentes de conversación en el sistema de diseño con sus pruebas.

## Alcance
- **Incluye:** Composer, endpoint de respuesta, componentes.
- **No incluye:** —

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-UI-* (sistema de diseño).

## Preguntas abiertas
- Ninguna por ahora.
