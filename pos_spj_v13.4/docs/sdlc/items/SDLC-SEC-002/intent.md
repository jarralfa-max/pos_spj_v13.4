# SDLC-SEC-002 — Autorización de dos personas confía en IDs enviados por la UI; usuarios inactivos siguen autorizando

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`authorized_by` es una cadena que manda el presenter; el backend no la ata a una prueba de `verify_authorizer`. El verificador resuelve cualquier ID que no sea de sesión contra `rol_permisos`, el alcance de sucursal siempre es verdadero para ellos, y `user_role_name` no filtra usuarios inactivos: el ID de un gerente dado de baja sigue autorizando.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/desktop/cash_register_factory.py:614,628,642,1269-1278`
- `backend/application/security/session_or_authorizer_checker.py:29-44`
- `backend/infrastructure/db/repositories/security/permission_repository.py:47`

## Impacto
Controles de caja (retiros, cancelaciones) eludibles; separación de funciones decorativa.

## Objetivo
- Una autorización sólo es válida con prueba verificada en backend (credencial del autorizador) ligada a la operación.
- Usuarios inactivos nunca autorizan; el alcance de sucursal del autorizador se evalúa.

## Alcance
- **Incluye:** Caja y verificador compartido de autorizador.
- **No incluye:** Otros módulos que usan el mismo verificador se revisan en Design.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria: `AuthorizerPermissionChecker` en security (Fase 5), PERM-AUD.

## Preguntas abiertas
- Ninguna por ahora.
