# SDLC-ARQ-AUD-001 — Eventos de seguridad (login, bloqueo, denegación) nunca se persisten; una denegación por sitio cuenta como éxito

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §14 · §6 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R14.1 Registro de eventos de seguridad, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`AuthenticateUserUseCase` emite eventos a `audit_sink`, que por defecto es un no-op, y la composición de producción no cablea ninguno: login exitoso/fallido y bloqueos se descartan (sólo quedan filas en `authentication_attempts`). Un login rechazado porque el rol no cubre el sitio se registra como intento SUCCEEDED, y la denegación no se audita.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/security/authentication/authenticate_user_use_case.py:71,104-107` (*verificado directamente*)
- `frontend/desktop/shell/desktop_shell_authentication_composition.py:85,100-108`
- `backend/security/audit/security_events.py`
- Pruebas: ninguna sobre persistencia de eventos de seguridad.

## Impacto
No hay rastro de quién intentó entrar, desde qué terminal, ni de denegaciones entre sucursales.

## Objetivo
- Sink de auditoría de seguridad persistente cableado en producción (autenticación, sesión, cambio de sucursal).
- Denegación por sitio registrada como fallo con motivo.
- Sin contraseñas ni tokens en el registro; pruebas.

## Alcance
- **Incluye:** Sink, composición, pruebas.
- **No incluye:** Unificar tablas de auditoría (AUD-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
