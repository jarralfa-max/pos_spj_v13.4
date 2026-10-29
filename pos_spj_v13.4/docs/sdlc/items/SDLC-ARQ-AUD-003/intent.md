# SDLC-ARQ-AUD-003 — Bloqueo de cuenta sólo por usuario; sin límite por terminal o IP en login

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §14 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R14.3 Límites de reintentos, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-AUD-001

## Problema
El bloqueo (5 fallos / 900 s) es por nombre de usuario. No hay limitación por terminal ni por IP en el login de escritorio ni en `/mobile/session`, así que se puede probar contraseñas de muchos usuarios sin bloqueo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/security/sessions/account_lockout_policy.py:21`
- `backend/bootstrap/wiring/security_wiring.py:26`

## Impacto
Ataques de contraseña distribuidos sobre la LAN o la API móvil.

## Objetivo
- Límite de intentos por terminal/IP además de por usuario, auditado.
- Pruebas.

## Alcance
- **Incluye:** Política y API móvil.
- **No incluye:** Rate limit de sync (SDLC-SEC-005).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SEC-004, SDLC-SEC-005.

## Preguntas abiertas
- Ninguna por ahora.
