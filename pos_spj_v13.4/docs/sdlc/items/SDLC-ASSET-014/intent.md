# SDLC-ASSET-014 — Custodia y préstamos de activos sin persistencia ni casos de uso; Activos no consulta empleados de RRHH

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §19, §21, §56, §65 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-011

## Problema
Asignación, devolución y préstamo existen solo como entidades. Nada impide dos asignaciones activas del mismo activo. El puerto de búsqueda de empleados no tiene adaptador, aunque RRHH expone servicios de consulta de empleados; las entidades guardan identificadores sin validar.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/asset_assignment.py:23-66`
- `backend/domain/assets/entities/asset_loan.py:21-62`
- `backend/domain/assets/integration_ports.py:47-49` — `EmployeeLookupPort` sin adaptador
- `backend/application/queries/hr/hr_query_services.py:53,68,90` — consultas de RRHH existentes

## Impacto
No se sabe quién tiene cada equipo.

## Objetivo
- Casos de uso Assign/Return/Loan/ReturnLoaned con historial y una sola asignación activa por activo (restricción en BD).
- Adaptador de empleados sobre RRHH, sin duplicar empleados.
- Pantallas de custodia y préstamos; pruebas de integración.

## Alcance
- **Incluye:** Custodia, préstamos, lookup de RRHH.
- **No incluye:** Transferencias entre sucursales (SDLC-ASSET-015).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- ASSET-4

## Preguntas abiertas
- Ninguna por ahora.
