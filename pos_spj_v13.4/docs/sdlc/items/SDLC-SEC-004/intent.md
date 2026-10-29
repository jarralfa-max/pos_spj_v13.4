# SDLC-SEC-004 — Código de autenticación duplicado y muerto (security/auth.py, listas de admin divergentes)

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`security/auth.py` en la raíz es un segundo sistema de autenticación (bcrypt, lockout en memoria, `crear_usuario`) sin importadores. `password_hasher.py` remite a un `core/services/auth_service.py` inexistente. `LegacySessionAdapter.es_gerente` tiene su propia lista de admins (sin `system_owner`/`administrador`) y no tiene llamadores.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `security/auth.py`
- `backend/security/credentials/password_hasher.py:12-14`
- `backend/bootstrap/legacy_session_adapter.py:157-162` vs `backend/security/permissions/principals.py:27-30`

## Impacto
Riesgo de reactivar una ruta insegura.

## Objetivo
- Un solo sistema de autenticación; código muerto eliminado con evidencia de cero importadores.

## Alcance
- **Incluye:** Eliminación.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria: dos listas de administrador que no coinciden (Precios).

## Preguntas abiertas
- Ninguna por ahora.
