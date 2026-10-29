# SDLC-ARQ-PERM-003 — Dos resolvedores de alcance discrepan y Transferencias pasa cuando no hay sucursal

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §3 · §4 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R3.7 / R4.5 Validación de alcance, estado `duplicado`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`BranchScopeQueryService.allowed_branch_ids` usa `usuarios_sucursales` + sucursal propia e ignora `user_role_assignments` y la jerarquía; `AccessScopeResolver` sí los usa. Según qué módulo pregunte, el mismo usuario alcanza sucursales distintas. Además `TransferSessionScopeChecker` devuelve `True` cuando `branch_id` viene vacío e ignora almacén/ubicación (lo documenta).

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/security/branch_scope_query_service.py:131-147`
- `backend/application/security/access_scope.py:68-121`
- `backend/application/transfers/session_scope_checker.py:50-52` (*verificado directamente*), docstring `:19-25`
- Pruebas: `tests/integration/security/test_branch_scope_query_service.py`, `tests/unit/organization/test_access_scope.py` (cada uno por separado).

## Impacto
Una asignación revocada en un resolvedor puede seguir vigente en otro; una operación de transferencia sin sucursal no se filtra por alcance.

## Objetivo
- Un único resolvedor de alcance usado por todos los checkers y consultas.
- Sin sucursal objetivo, el checker de transferencias falla cerrado salvo alcance global explícito.
- Prueba que compara ambos caminos para usuarios con asignación por región, por rol y directa.

## Alcance
- **Incluye:** Resolvedor canónico, checkers de transferencias, pruebas.
- **No incluye:** Alcance por almacén/ubicación (SDLC-ARQ-SCOPE-001); BI (SDLC-BI-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-BI-001, SDLC-SEC-003 (checkers que omiten sucursal).

## Preguntas abiertas
- ¿Las transferencias sin sucursal objetivo existen en la operación (p. ej. hacia planta) o siempre llevan sucursal?
