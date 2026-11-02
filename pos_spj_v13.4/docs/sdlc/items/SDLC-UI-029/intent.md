# SDLC-UI-029 — Huecos de las guardias: personalización por instancia, QTreeWidget/QTableView, Qt.<color>, glifos y ventanas QWidget

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §42 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-003

## Problema
La auditoría AST global cubre las 11 reglas del documento solo en parte. No detecta personalización visual por instancia (`setFont`, `setPalette`), `QTreeWidget`/`QTableView`, colores `Qt.<color>`, glifos en U+2190–23FF ni ventanas `QWidget` + `Qt.Window`. Mantiene además guardias duplicadas por módulo para assets, customers_crm y products.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `tests/architecture/design_system_audit.py:21,123-185`
- `tests/architecture/test_standard_window_ownership.py` (solo `QMainWindow`)
- Guardias por módulo: `test_assets_have_no_inline_styles.py`, `test_customers_crm_has_no_inline_styles.py`, `test_products_ui_has_no_inline_styles.py`, `test_products_ui_has_no_hardcoded_colors.py` y otras

## Impacto
Un módulo nuevo puede introducir deuda que el CI no ve.

## Objetivo
- La auditoría global detecta los casos listados
- Las guardias por módulo redundantes se retiran (una sola fuente de reglas)

## Alcance
- **Incluye:** `tests/architecture/`.
- **No incluye:** Corregir lo que destapen (va a sus ítems).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
