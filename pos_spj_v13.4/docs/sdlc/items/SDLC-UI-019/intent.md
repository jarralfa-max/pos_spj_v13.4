# SDLC-UI-019 — StandardTable sin acciones por fila ni ordenamiento; anchos guardados, filtro y carga casi sin uso

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §36 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** borradoraprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
`StandardTable` tiene ColumnSpec completo, scroll y estados, pero no ofrece una API de acciones por fila, por lo que 6 módulos insertan botones con `setCellWidget`. El ordenamiento nunca se activa. Los anchos guardados (`settings_key`) se usan en 2 archivos, y `set_filter`, `set_loading`, `hide_below` y `set_column_visible` tienen 0 usos, así que las tablas no son responsive en la práctica.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/components/tables.py:22-38,41,56,101-121,123,137-165,173-192`
- Usos de `settings_key=`: `configuracion/dialogs/role_assignment_dialogs.py:96`, `configuracion/pages/empresa_page.py:143`
- 225 llamadas `StandardTable(` en 18 módulos (según el barrido)
- `tests/ui/test_responsive_components.py:94-162`

## Impacto
Tablas que no se pueden ordenar, que pierden los anchos al reabrir y que no ocultan columnas en pantallas chicas.

## Objetivo
- API de acciones por fila en `StandardTable`, y los `setCellWidget` migrados
- Ordenamiento activable por columna
- Los módulos operativos pasan `settings_key` y `hide_below` en columnas secundarias, con prueba a 1280×720

## Alcance
- **Incluye:** `components/tables.py` y su adopción; puede dividirse por módulo en Design.
- **No incluye:** Tablas nativas (SDLC-UI-023, SDLC-UI-025).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
