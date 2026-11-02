# SDLC-UI-030 — Pruebas visuales sin imágenes de referencia, fuera de CI y con componentes sin cubrir

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §43, §44, §45.25 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-001

## Problema
Las pruebas de matriz visual recorren tema × resolución × densidad y guardan PNG, pero solo verifican geometría: no hay imágenes de referencia contra las que comparar. En CI solo corre la de Compras. No tienen prueba visual el menú de cierre de sesión, el NavGroup expandido aislado ni los estados de PageHeader y KPICard. El orden de arranque (tema antes de ventanas) tampoco tiene prueba de extremo a extremo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `tests/ui/test_design_system_visual_matrix.py:3-4` (el docstring declara que no compara con referencia)
- `tests/ui/test_design_system_navigation_visuals.py`
- Comparación de píxeles solo en `tests/ui/test_global_qss_visuals.py:153` y `test_theme_contrast_rendering.py`
- `../.github/workflows/ci-segmented.yml:48-53`
- `frontend/desktop/app.py:398,415,497` sin prueba del orden

## Impacto
Una regresión visual (colores, cortes) pasa sin que ninguna prueba la vea.

## Objetivo
- Imágenes de referencia versionadas para los componentes de §44 en light/dark × Comfortable/Touch, con tolerancia
- Comparación automática en CI (Windows) con artefacto de diferencias
- Prueba del orden de arranque

## Alcance
- **Incluye:** Pruebas y CI.
- **No incluye:** Correcciones visuales que destape.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- ¿Las imágenes de referencia se versionan en el repo (tamaño) o como artefacto de CI? Se vercionana 
- ¿Se generan en Windows (plataforma real) o en `offscreen`? Windowa 
