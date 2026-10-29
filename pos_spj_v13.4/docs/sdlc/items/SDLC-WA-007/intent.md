# SDLC-WA-007 — Microservicio WhatsApp viola REGLA CERO y escribe configuración/migraciones del ERP

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-003

## Problema
Fallback `uuid4` para `clientes.id`, DDL en tiempo de ejecución con INTEGER AUTOINCREMENT y `lastrowid`; escribe la tabla `configuraciones` del ERP tragándose errores y corre migraciones sobre la BD del ERP.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `whatsapp_service/erp/bridge.py:66-69`
- `whatsapp_service/state/reminder_engine.py:81,177`
- `whatsapp_service/erp/pos_notifier.py:230`
- `whatsapp_service/ai/intent_resolver.py:36-47`
- `whatsapp_service/main.py:110-111`

## Impacto
Esquema del ERP modificado por un servicio externo.

## Objetivo
- El microservicio no ejecuta DDL ni migraciones del ERP; ids UUIDv7.

## Alcance
- **Incluye:** Microservicio.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Microservicio WhatsApp: preservar los 3 shims de CLAUDE.md regla 9; el cutover del webhook a WA-1..20 sigue diferido por decisión del usuario.

## Trabajo previo relacionado
WA-22.

## Preguntas abiertas
- Ninguna por ahora.
