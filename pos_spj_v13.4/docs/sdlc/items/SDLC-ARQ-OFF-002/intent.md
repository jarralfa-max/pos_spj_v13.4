# SDLC-ARQ-OFF-002 — Tokens móviles con fotografía de permisos de 15 min sin verificación de revocación

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §11 · §14 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R11.2 Revocaciones, estado `parcial`)
- **Estado:** borrador
- **Depende de:** —

## Problema
La sesión móvil emite un token con los permisos del momento y 15 minutos de vida, sin consultar revocaciones durante su vigencia.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/api/mobile_session.py:35-70`

## Impacto
Un repartidor o usuario móvil revocado sigue operando hasta 15 min.

## Objetivo
- Verificación de versión de concesiones (grant version) en cada petición móvil.
- Prueba de revocación.

## Alcance
- **Incluye:** API móvil.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
`session_grant_refresh` del escritorio (mismo patrón).

## Preguntas abiertas
- Ninguna por ahora.
