# SDLC-ARQ-PERM-002 — Escalada por alcance: se pueden asignar roles y permisos fuera del alcance de quien los otorga

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §3 · §14 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R3.7 Mínimo privilegio y validación de alcance, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-PERM-003

## Problema
La guarda de escalada impide otorgar permisos que el actor no tiene, pero no verifica el **alcance**: un no-administrador con permiso de asignar puede dar un rol con ámbito COMPANY o en una unidad fuera de su alcance, y `SaveUserPermissions` no verifica que el alcance del actor cubra al usuario destino ni `scope_branch_id`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/security/role_assignment_service.py:133-157`
- `backend/application/security/save_user_permissions_use_case.py:66-98,148-158`
- Prueba existente sólo de escalada de permisos: `tests/integration/security/test_contextual_permissions.py:274`.

## Impacto
Un gerente de sucursal podría otorgarse (o a otro) acceso a toda la empresa.

## Objetivo
- Asignar o revocar rol/permiso exige que el alcance del actor cubra el ámbito y al usuario destino.
- Rechazo auditado con motivo.
- Pruebas: gerente de A no puede asignar en B ni COMPANY.

## Alcance
- **Incluye:** Servicio de asignación de roles y caso de uso de permisos por usuario.
- **No incluye:** Unificar resolvedores (PERM-003), aunque debe usar el canónico.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Auditoría de permisos 968e0bc.

## Preguntas abiertas
- Ninguna por ahora.
