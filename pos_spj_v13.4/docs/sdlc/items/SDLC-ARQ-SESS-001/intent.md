# SDLC-ARQ-SESS-001 — Menú y router conservan los permisos del login; no hay prueba de dos usuarios secuenciales

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §7 · §5 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R7.1 / R5.1 Sin herencia de sesión; permisos efectivos en UI, estado `parcial`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El router y la barra lateral guardan el contexto del inicio de sesión: una revocación llega a los módulos (vía `LegacySessionAdapter` y `SessionGrantRefresher`) pero el menú y la guarda de rutas siguen permitiendo hasta el siguiente login. Ninguna prueba hace login A → logout → login B y verifica que B no herede permisos ni alcance de A.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/shell/desktop_shell_window_composition.py:343,350`
- `backend/bootstrap/legacy_session_adapter.py:58-90`
- `backend/application/security/session_grant_refresh.py:28-73`
- Pruebas: `tests/unit/shell/test_desktop_logout_transition.py` (mocks), `tests/unit/security/test_session_manager.py`.

## Impacto
Un usuario con permiso recién revocado sigue viendo y abriendo pantallas.

## Objetivo
- Router y barra lateral consultan los permisos efectivos vigentes.
- Prueba de integración §15 T5: dos usuarios secuenciales sin herencia.

## Alcance
- **Incluye:** Shell, router, sidebar, prueba.
- **No incluye:** TTL y bloqueo (SESS-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
