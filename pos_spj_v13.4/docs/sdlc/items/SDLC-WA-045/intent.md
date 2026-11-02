# SDLC-WA-045 — Sin auditoría de acciones del canal: envío, handoff, bloqueo, opt-out, plantillas y configuración no dejan rastro

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §72 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-044

## Problema
Ninguna de las 18 tablas del canal es de auditoría. `wa_event_log` no guarda usuario, antes/después ni motivo y nadie la lee. Los cambios de configuración y secretos se auditan desde el presentador de Configuración, no desde backend.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `backend/infrastructure/db/schema/whatsapp_schema.py:53-72,167-168`
- `whatsapp_service/erp/events.py:90`; `erp/pos_notifier.py:179-201`
- `frontend/desktop/modules/configuracion/configuracion_presenter.py:332` — `_record_audit` en la UI
- Prueba: ninguna

## Impacto
Auditoría: imposible saber quién respondió, bloqueó o cambió algo en el canal.

## Objetivo
- Registro de auditoría del canal con los campos de §72 (usuario o identidad de servicio, operación, conversación, mensaje, acción, antes, después, motivo, sucursal, número, fecha, correlación), sin secretos ni contenido sensible completo.

## Alcance
- **Incluye:** Auditoría del canal.
- **No incluye:** Retención de mensajes (SDLC-WA-011).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-ARQ-AUD-001.

## Preguntas abiertas
- Ninguna por ahora.
