# SDLC-ARQ-TEST-001 — Arnés de aceptación multi-terminal y pruebas obsoletas que importan módulos eliminados

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §15 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito §15 Pruebas de aceptación (arnés), estado `parcial`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Los escenarios de §15 que requieren dos terminales, dos usuarios concurrentes o reinicio de proceso no tienen arnés (dos SQLite + central en memoria). Además hay pruebas que importan paquetes eliminados (`core.services.*`, `repositories.*`): `tests/test_installation_branch_resolution.py`, `tests/test_sync_service_cursor_compat.py`. Las pruebas PG sólo corren en CI.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `tests/test_installation_branch_resolution.py`; `tests/test_sync_service_cursor_compat.py:3`
- `tests/integration/central_pg/*` (`importorskip` + `skipif` sin `SPJ_TEST_PG_DSN`); `../.github/workflows/ci-segmented.yml:70-104`
- Estado por escenario en `docs/sdlc/arquitectura/matriz-brechas.md` §15.

## Impacto
Sin arnés, los ítems de caja compartida, servicio local y sync no pueden demostrar aceptación.

## Objetivo
- Fixture reutilizable de N estaciones + central para pruebas de integración.
- Pruebas obsoletas reescritas contra el código actual o retiradas con justificación (nunca sólo saltadas).
- Tabla §15 → prueba mantenida en la matriz.

## Alcance
- **Incluye:** Arnés y limpieza de pruebas obsoletas.
- **No incluye:** Las pruebas de cada escenario (las aporta cada ítem).

## Restricciones
CLAUDE.md; `docs/skills/SPJ_REFACTOR_SKILL.md` (UUIDv7, rutas dentro de `pos_spj_v13.4/`); presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
SDLC-CORE-007, SDLC-CORE-011.

## Preguntas abiertas
- Ninguna por ahora.
