# SDLC-ARQ-SESS-002 — Sin bloqueo de pantalla ni expiración: la sesión de 8 h nunca se aplica

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §7 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R7.2 Logout/bloqueo, estado `parcial`)
- **Estado:** aprobado (2026-10-29, Alfred)
- **Depende de:** —

## Problema
No existe pantalla de bloqueo ni bloqueo por inactividad. El TTL de sesión de 8 h nunca se hace cumplir (`get_active_session` y `touch` no se llaman). Las sesiones viven sólo en memoria.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/shell/desktop_shell_authentication_composition.py:85` `InMemorySessionRepository` (*verificado directamente*)
- `frontend/desktop/app.py:303-330` (logout)
- Búsqueda sin resultados de lock/idle/inactividad en `frontend/` (según barrido, **no verificado** exhaustivamente).

## Impacto
Una caja desatendida queda con la sesión del cajero abierta indefinidamente; cualquiera puede operar a su nombre.

## Objetivo
- Bloqueo por inactividad configurable que exige reautenticación del mismo usuario o cierre de sesión, sin cerrar caja.
- TTL de sesión aplicado.
- Pruebas de unidad e integración.

## Alcance
- **Incluye:** Shell y gestor de sesión.
- **No incluye:** Persistencia de sesión.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- ¿Tiempo de inactividad para bloqueo en POS y en terminal administrativa? 30 min de inicio, pero debe ser configurable, desde configuracion

## Ampliación 2026-10-29 (UI/UX)
Origen: `docs/sdlc/inputs/ui-ux.md` §22, §26, §28 y §33; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`.

El documento de UI pide «Bloquear sesión» en el menú Archivo y en el menú de usuario, el estado «Sesión bloqueada» y «Sesión próxima a vencer» en la barra superior, y un diálogo de bloqueo institucional con el logo completo. Lo medido:
- Archivo solo tiene Cerrar sesión y Salir, y el menú de usuario solo Mi perfil y Cerrar sesión (`frontend/desktop/shell/application_shell/top_bar.py:63-72,76-83`).
- `Icons.LOCK` («Bloquear sesión») existe y nada lo usa (`frontend/desktop/components/icons.py:167`).
- `TopBar.set_session_state('locked')` existe y no tiene llamador en producción (`top_bar.py:142`).
- `SessionStatus.LOCKED` existe (`backend/security/sessions/user_session.py:17`) y nada transiciona a él. `SessionManager` no tiene lock, unlock ni reauth (`backend/security/sessions/session_manager.py:38-106`).

El objetivo de este ítem se amplía con la acción visible en ambos menús y el diálogo de desbloqueo con logo (§33). Las señales «próxima a vencer» y «bloqueada» de la barra se consumen en SDLC-UI-013.
