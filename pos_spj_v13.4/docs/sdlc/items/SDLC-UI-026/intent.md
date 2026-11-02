# SDLC-UI-026 — Inventario y resto de módulos: QComboBox nativos y componentes locales

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §6, §39, §46.23 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-011

## Problema
Inventario tiene 19 `QComboBox` nativos. Quedan además botones sueltos en Cárnico, POS y Mermas, `QSpinBox` nativos, estados vacíos hechos con `QLabel` y componentes locales (tarjeta de orden de trabajo, tarjeta de totales y tabla de carrito del POS).

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- Conteo del barrido: `QComboBox` inventory 19; `QPushButton` meat_processing 2, sales_pos 1, losses 1; `QSpinBox` 10
- `frontend/desktop/modules/meat_processing/pages/quality_inspection_page.py:42`; `sales_pos/components/product_grid.py:68`; `receipt_options_dialog.py:66` (estados vacíos con QLabel)
- `frontend/desktop/modules/assets/pages/work_orders_board_page.py:52`; `sales_pos/components/totals_card.py:39`; `sales_pos/components/cart_table.py:58`

## Impacto
Inconsistencia visual menor.

## Objetivo
- 0 controles nativos en estos módulos; estados vacíos con `EmptyState`; los componentes locales se justifican o se reemplazan

## Alcance
- **Incluye:** Módulos listados; puede dividirse en Design.
- **No incluye:** Productos, RRHH y Finanzas (UI-023…025).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
