# SDLC-ARQ-PERM-004 — Rol corporativo o de acceso total obtiene operación POS en cualquier sucursal; el nombre del rol concede privilegios

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §3 · §6 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R3.2 / R6.4 Nombre de rol y cuenta corporativa, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El documento dice que el nombre de un rol no concede privilegios y que una cuenta corporativa con consultas globales no obtiene automáticamente acceso operativo al POS de otra sucursal. Hoy `admin`, `superadmin`, `administrador` y `system_owner` conceden acceso total por nombre, `is_admin()` salta todas las verificaciones y un rol con ámbito COMPANY cubre cualquier sitio para operar. Una prueba fija este comportamiento como intencional. Queda además la lista de nombres sin uso `es_gerente`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/security/permissions/principals.py:24-30`
- `backend/bootstrap/permission_evaluator.py:33-34`
- `backend/application/security/access_scope.py:42-45,71-72,86-89`
- `tests/integration/security/test_contextual_permissions.py:204` `test_the_owner_is_company_wide_and_reaches_every_site` (*verificado directamente*)
- `backend/bootstrap/legacy_session_adapter.py:158-162`

## Impacto
Una cuenta de dueño/corporativo puede vender, abrir turno o mover efectivo en cualquier POS sin asignación operativa; decisión de negocio pendiente.

## Objetivo
- Política aprobada que separe 'consulta global' de 'operación en el sitio'.
- El acceso total proviene de permisos asignados, no del nombre del rol (sin perder la configuración actual: migración que convierte nombres reservados en asignaciones).
- Pruebas que reflejan la política aprobada (se reemplaza la prueba actual sólo tras aprobación).

## Alcance
- **Incluye:** Política, evaluador, migración de roles reservados, pruebas.
- **No incluye:** Matriz de perfiles de referencia (PERM-006).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SEC-004 (código de autenticación duplicado, listas de admin divergentes).

## Preguntas abiertas
- ¿El dueño (`system_owner`) debe poder operar el POS de cualquier sucursal sin asignación operativa explícita?
- ¿Se mantienen roles reservados por nombre (hoy no renombrables) o se convierten en roles normales con todos los permisos?
