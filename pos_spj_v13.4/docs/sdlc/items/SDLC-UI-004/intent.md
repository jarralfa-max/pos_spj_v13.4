# SDLC-UI-004 — Tokens semánticos incompletos; modo oscuro con color de marca crudo y gráficas casi invisibles en oscuro

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §2, §3, §4 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
La cadena de tokens existe, pero tiene huecos: faltan SUCCESS, WARNING, INFO y BORDER como tokens planos. En oscuro, PRIMARY, ACCENT y DANGER son el color de marca sin ajustar y casi todo el tema se escribió con hex sueltos en vez de las escalas. La paleta de series de ECharts es la misma en ambos temas e incluye el carbón `#252825`, que es el color de la superficie oscura. La pantalla del cliente usa la marca directo, y quedan colores Qt fijos (`Qt.gray`, `QPalette.Mid`) que ignoran el tema.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/themes/semantic_colors.py:38-76` (solo `*_DEFAULT`/`*_SUBTLE`), `:92-94` (oscuro con marca cruda), `:99-154` (hex a mano), `:174` (`ChartPalette.CATEGORICAL` sin tema), `:192-198` (`ChartPalette.STATUS` duplica hex)
- `frontend/desktop/themes/qss_builder.py:54-77` (`_customer_display()` con `BrandColors`)
- `frontend/desktop/components/entity_search_input.py:211`; `components/search_selector.py:146`; `modules/products/pages/categories_page.py:80` (`Qt.gray`)
- `frontend/desktop/modules/fidelidad/cards/card_preview.py:59-91` (`QPalette.Mid`, que `theme_manager.py:103-115` no fija)
- `tests/architecture/test_theme_contrast.py:111` solo comprueba que las series se distingan, no su contraste en oscuro

## Impacto
Usuarios en modo oscuro: series de gráficas ilegibles en BI y paneles; textos grises fijos sin contraste. Mantenimiento: el tema oscuro no se deriva de la paleta.

## Objetivo
- Existen SUCCESS, WARNING, INFO y BORDER como tokens semánticos
- El oscuro se deriva de las escalas de `brand_palette.py`
- La paleta de gráficas depende del tema y una prueba mide su contraste contra la superficie oscura
- La pantalla del cliente y los colores Qt fijos consumen tokens

## Alcance
- **Incluye:** `frontend/desktop/themes/`, `charts/`, los 4 archivos con colores fijos.
- **No incluye:** Webs y PDF (SDLC-UI-005); tablas de temas en la base (SDLC-SET-003).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- ¿La pantalla del cliente debe seguir el tema de la caja o tener siempre la apariencia de marca (hoy es fija)? debe seguir el tema 
