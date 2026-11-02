# SDLC-UI-023 — Productos: 57 QPushButton, 18 QLineEdit, 34 QComboBox y 2 QTreeWidget fuera del estándar

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §6, §36, §38, §39, §46.23 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-011, SDLC-UI-019

## Problema
Productos concentra casi todos los botones nativos de la app y usa dos `QTreeWidget` (categorías y generador de variantes), que la guardia no detecta. El QSS global estiliza los `QPushButton` crudos, así que se ven aceptables, pero no tienen variante, densidad táctil ni contrato.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- Conteo del barrido: `QPushButton(` 57 en products (`dialogs/cutting_dialog.py` 6, `pages/categories_page.py` 5, `yields_dialog.py` 5, `recipes_dialog.py` 5, `bundles_dialog.py` 5…)
- `frontend/desktop/modules/products/pages/categories_page.py:61`; `products/dialogs/variant_generator_dialog.py:38` (`QTreeWidget`)
- `frontend/desktop/themes/qss_builder.py:158` (regla para `QPushButton` crudo)

## Impacto
Pantallas de catálogo con controles fuera del estándar táctil y del tema de botones.

## Objetivo
- 0 `QPushButton`, `QLineEdit` y `QComboBox` crudos en `modules/products`
- Árbol de categorías con un componente canónico (o uno nuevo agregado al catálogo)

## Alcance
- **Incluye:** `frontend/desktop/modules/products/`.
- **No incluye:** Lógica de Productos.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- ¿Se agrega un componente canónico de árbol (`StandardTree`) o se rediseña categorías como tabla? Componenete canonico 
