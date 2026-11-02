# SDLC-WA-051 — CLAUDE.md pide preservar shims de WhatsApp que ya no existen y los informes WA-0…22 describen código borrado

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §4, §80 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Las reglas 8 y 9 de `CLAUDE.md` (raíz) ordenan preservar `services/whatsapp_service.py` e `integrations/whatsapp_service.py`; ambos están borrados, igual que `core/`. El documento de requisitos pide eliminarlos. Los entregables WA-0 (`whatsapp_legacy_inventory.md`, `whatsapp_runtime_map.md`, `whatsapp_security_audit.md`…) y `WA-19_ui.md` describen archivos borrados; `notify_dispatch_router.py:13` nombra `core/integrations/whatsapp_client.py`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `CLAUDE.md:71-78` (raíz del repositorio)
- Ausentes en disco: `services/whatsapp_service.py`, `integrations/whatsapp_service.py`, `core/services/whatsapp_service.py`, `modulos/whatsapp/` *(verificado directamente)*
- `docs/refactor/whatsapp_legacy_inventory.md`, `whatsapp_runtime_map.md`, `whatsapp_security_audit.md`, `WA-19_ui.md`
- `whatsapp_service/router/notify_dispatch_router.py:13`

## Impacto
Agentes y personas siguen instrucciones contradictorias.

## Objetivo
- `CLAUDE.md` refleja el estado real (lo cambia el responsable); inventarios WA-0 actualizados o marcados como históricos.

## Alcance
- **Incluye:** Documentación.
- **No incluye:** —

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T2: plan corto, pruebas afectadas. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
—

## Preguntas abiertas
- ¿Actualizas tú las reglas 8 y 9 de `CLAUDE.md`, o propongo el texto en el PR para que lo apruebes?
