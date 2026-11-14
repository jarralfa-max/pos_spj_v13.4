# SDLC-ASSET-018 — Tablero de órdenes de trabajo y agenda son de solo lectura; no hay formulario de OT

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §95, §96, §98 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-016

## Problema
El tablero de OT es un Kanban estático sin vista de tabla ni calendario y sin mover tarjetas; la agenda es una tabla ordenada por fecha sin vista día/semana/mes ni indicadores de vencido. No hay formulario de OT.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `frontend/desktop/modules/assets/pages/work_orders_board_page.py:4-13,103-107`
- `frontend/desktop/modules/assets/pages/maintenance_agenda_page.py:4-13,63-71`

## Impacto
El técnico no puede operar sus órdenes desde la app.

## Objetivo
- Mover una tarjeta invoca el caso de uso; el estado no cambia solo en la UI.
- Vistas tabla y calendario; agenda día/semana/mes con indicadores de §96.
- Formulario de OT con las secciones de §98 que tengan respaldo.

## Alcance
- **Incluye:** UI de mantenimiento.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- ASSET-19

## Preguntas abiertas
- Ninguna por ahora.
