# SDLC-ARQ-HYB-004 — Nada impide que el escritorio hable directo con PostgreSQL

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §2 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R2.E Clientes nunca directo a PostgreSQL, estado `implementado sin prueba`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Hoy sólo el central usa psycopg y `SPJ_PG_DSN`, pero es por convención: no hay guardia de arquitectura que impida a `frontend/` o al backend de estación importar el adaptador PG o leer la configuración PG.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/database.py:28,49-60`
- Usuarios de psycopg: `backend/api/central_app.py`, `backend/infrastructure/central/sync_inbox_repository.py`

## Impacto
Regresión silenciosa posible contra §2.E.

## Objetivo
- Prueba en `tests/architecture` que falla si código de estación importa psycopg o la configuración PG.

## Alcance
- **Incluye:** Prueba de arquitectura.
- **No incluye:** —

## Restricciones
CLAUDE.md; `docs/skills/SPJ_REFACTOR_SKILL.md`. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
