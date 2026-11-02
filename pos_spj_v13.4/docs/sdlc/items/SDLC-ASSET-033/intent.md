# SDLC-ASSET-033 — Defectos de las páginas actuales de Activos: enums crudos, error tragado, accesibilidad y docstrings falsos

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/activos.md` §93, §94, §103, §104, §108 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El detalle y la agenda muestran valores de enum crudos. El detalle se traga cualquier excepción y muestra «Selecciona un activo» en vez de un estado de error. Etiquetas del detalle sin nombre accesible y tarjetas de OT sin foco. Docstrings con conteos falsos (33 rutas y 3 páginas; son 36 y 5). En Finanzas, la columna «Código» de activos fijos está tipada como fecha.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `frontend/desktop/modules/assets/pages/asset_detail_page.py:72-75` — `except Exception`; `:86-88` enums crudos; `:48-51` sin nombre accesible
- `frontend/desktop/modules/assets/pages/maintenance_agenda_page.py:66`
- `frontend/desktop/modules/assets/pages/work_orders_board_page.py:52-66` — tarjetas sin foco
- `frontend/desktop/modules/assets/assets_routes.py:4-8`, `assets_workspace.py:9-15`, `assets_presenter.py:8-11`, `shell_registration.py:10-13` — docstrings
- `frontend/desktop/modules/finance/pages/fixed_assets_page.py:20` — `ColumnSpec("Código", "date")`

## Impacto
Cosmético y de diagnóstico.

## Objetivo
- Etiquetas legibles, estado de error visible, accesibilidad corregida, docstrings verdaderos, columna con tipo correcto.

## Alcance
- **Incluye:** Los archivos listados.
- **No incluye:** Densidades y teclado virtual (SDLC-UI-007, SDLC-UI-021).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
- SDLC-UI-007, SDLC-UI-021

## Preguntas abiertas
- Ninguna por ahora.
