# SDLC-UI-010 — Overflow: 101 pantallas sin contrato explícito, scroll anidado y encabezado/acciones fijos fuera del viewport

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §8, §45.6-7 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-003

## Problema
`ContentHost` envuelve toda página en un `PageViewport`, pero el viewport no ofrece encabezado ni acciones fijos: eso solo lo dan `StandardPage` y `ModuleLayout`. Cuando una `StandardPage` va dentro de `ContentHost` quedan dos scrolls anidados. La auditoría AST encuentra 101 pantallas sin política explícita de overflow, 17 de ellas nuevas desde la línea base. Quedan 4 `setFixed*` usados como layout.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/shell/application_shell/content_host.py:57-59,133`; `frontend/desktop/components/page_viewport.py:23-24,37-39`
- *medido:* 101 `screen_without_explicit_overflow` en `tests/architecture/design_system_audit.py`
- `frontend/desktop/modules/sales_pos/components/product_grid.py:120`; `configuracion/pages/empresa_page.py:79`; `products/dialogs/brand_form_dialog.py:39`; `configuracion/dialogs/logo_upload_dialog.py:92`
- Scroll anidado `StandardPage` dentro de `ContentHost`: según el barrido, **no verificado** en ejecución

## Impacto
Formularios con acciones que se van fuera de vista en 1280×720; doble barra de scroll.

## Objetivo
- Una sola política de overflow: quién hace scroll y qué queda fijo (encabezado y acciones)
- Sin scroll anidado
- Las 101 pantallas declaran su política, o la heredan de un layout canónico y la auditoría lo reconoce

## Alcance
- **Incluye:** `PageViewport`, `ContentHost`, `StandardPage` y `ModuleLayout`; las pantallas listadas por la auditoría, que pueden repartirse en Design.
- **No incluye:** Migración visual completa de módulos (SDLC-UI-023…026).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
