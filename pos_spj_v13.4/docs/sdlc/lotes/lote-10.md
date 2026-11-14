# Lote 10 — UI / Design System (rama `fix/lote-10`)

Base: `claude/erp-financial-bounded-context-uqxz6b` @ `e58f6849`. Corrección directa
de intents aprobados (sin spec/plan). Fecha: 2026-11-12.

| Ítem | Estado | Commit |
|------|--------|--------|
| SDLC-UI-004 | LISTO | `424899f8` |
| SDLC-UI-005 | LISTO | `02ae3d13` |
| SDLC-UI-007 | LISTO | `8718f8ab` |
| SDLC-UI-001 | Saltado (ya construido en `sdlc/sdlc-ui-003-auto`) | — |
| SDLC-UI-003 | Saltado (ya construido en `sdlc/sdlc-ui-003-auto`) | — |
| SDLC-UI-002 | ESPERA: depende de SDLC-UI-001, que vive en otra rama | — |

## SDLC-UI-004: tokens semánticos y tema oscuro — LISTO

El problema seguía vigente: `semantic_colors.py:38-76` solo tenía `*_DEFAULT`, `:92-94` usaba la marca cruda en oscuro, `:99-154` tenía hex escritos a mano, `ChartPalette` no dependía del tema (`#252825`, el color de la superficie oscura, era una serie) y `Qt.gray` / `QPalette.Mid` estaban fijos.

Cambios:
- `themes/semantic_colors.py`: se agregan los tokens planos `SUCCESS`, `WARNING`, `INFO` y `BORDER` en `Light` y `Dark`. `Dark` ya no tiene ningún hex: cada token se deriva de `BrandColors` (o de la contraparte funcional de `Light`) con `tone()`. `Dark.PRIMARY/ACCENT/DANGER` apuntan a las variantes ajustadas. Los valores quedan a ≤ 4 unidades RGB de los anteriores (verde primario: ~17, porque ahora usa el tono de la marca). `ChartPalette.for_theme()` agrega `DarkChartPalette`, donde todas las series pasan 3:1 sobre `SURFACE` y `BACKGROUND` en oscuro. `STATUS` sale de los tokens y ya no duplica hex.
- `themes/color_utils.py`: `tone(color, lightness, saturation)` conserva el tono en HLS.
- `charts/chart_bridge.py`: la paleta y los colores de las series se toman del tema.
- `themes/qss_builder.py` `_customer_display(c)`: la pantalla del cliente sigue el tema de la caja (respuesta del responsable). El icono de confirmación (`customer_display_window.py`) pasa a `IconProvider.bind(state="inverse")` en lugar de `theme="dark"` fijo.
- `Qt.gray` → `TEXT_MUTED` en `entity_search_input.py`, `search_selector.py` y `categories_page.py`. `ThemeManager` fija `QPalette.Mid = BORDER_STRONG`, que es lo que lee `card_preview.py`.

Pruebas: `tests/architecture/test_theme_tokens_dark_derivation.py` (30; en la primera versión, antes del arreglo, fallaban 24 de 24), `tests/ui/test_theme_manager_runtime.py::test_painted_frames_read_the_theme_mid_role` (fallaba) y `tests/unit/sales_pos/test_customer_display_window.py::test_display_follows_the_register_dark_theme`.
Se ajustó una prueba existente: `tests/ui/test_charts.py::test_open_chart_rebuilds_html_theme_without_requerying_data` exigía que las series conservaran el mismo color en los dos temas, es decir, fijaba el defecto. Ahora compara los datos sin el color y verifica que en oscuro se use la paleta oscura.

## SDLC-UI-005: PWA y PDF de BI con identidad JUANIS — LISTO

El problema seguía vigente: había una paleta azul marino en `frontend/web/{delivery,logistics}/styles.css`, en los manifiestos, en `theme-color` y en los iconos SVG, además de `#1E3A5F`/`#CCCCCC` en `bi_export_service.py:157,161`.

Cambios:
- `frontend/desktop/themes/web_tokens.py` (nuevo) exporta variables CSS desde `semantic_colors.Light`, la misma fuente que el QSS. Cada `styles.css` embebe el bloque generado (`python -m frontend.desktop.themes.web_tokens --write` lo regenera), las variables cambian a nombres semánticos (`--primary`, `--text`…) y no quedan hex fuera del bloque. Los manifiestos, `theme-color` y los iconos usan el verde JUANIS.
- `BiExportService(document_colors=...)`: la capa de aplicación ya no tiene paleta propia y, si no se inyectan colores, usa tinta neutra de reportlab. `ReportsPresenter` inyecta `document_palette()`.

Pruebas: `tests/architecture/test_web_and_documents_use_juanis_tokens.py` (9). Falla si aparece en `frontend/web` (sin contar `vendor/`) un hex que no salga de la fuente JUANIS. Antes del arreglo fallaba al recolectar porque el módulo no existía.
Pendiente que no se verificó: no se probaron las PWA en un navegador real. El service worker es *network-first*, así que el CSS nuevo llega sin cambiar la versión de la caché.

## SDLC-UI-007: densidad por terminal — LISTO

El problema seguía vigente: `theme_manager.py:46,77` guardaba la densidad en `QSettings("JUANIS","SPJ")`, que es por usuario de Windows, con `comfortable` como valor por defecto.

Respuestas del responsable: la densidad va **por terminal** y aplica a **todas** las pantallas de operación. Con eso, `POSPage(density='touch')` por pantalla queda sin uso y no se modificó; consolidarlo le toca a SDLC-UI-011.

Cambios (`themes/theme_manager.py`):
- La densidad se guarda en `terminal_appearance.ini`, dentro de la carpeta de datos de la estación (`AppPaths.user_data_dir`). En una instalación por máquina esa carpeta es `%PROGRAMDATA%`, compartida por todos los usuarios de Windows. El tema sigue siendo por usuario.
- Una terminal sin configurar toma una sola vez la densidad que tenía el usuario. Si no hay ninguna, arranca en TOUCH si la PC tiene pantalla táctil (`QTouchDevice`) y en `comfortable` si no.

Pruebas: `tests/ui/test_terminal_density_scope.py` (7; antes del arreglo fallaban las 7), incluida la que mide la altura de botones y entradas del `SalesPosWorkspace` en una terminal táctil. Se confirmó que esa prueba falla con densidad `comfortable`.
Notas para el responsable:
- Arrancar en TOUCH al detectar pantalla táctil es una interpretación de «TOUCH por defecto en las terminales táctiles». Si no se quiere, basta con quitar el `touch_probe`.
- En una instalación por usuario y en el checkout de desarrollo, la carpeta de datos es del usuario, así que ahí «terminal» equivale a «usuario».

## Migraciones

Ninguna. No se usaron los números 377–379.

## Resultados de pruebas (desde `pos_spj_v13.4/`, `QT_QPA_PLATFORM=offscreen`)

- `python -m compileall -q .`: sin errores.
- Guardias de diseño y arquitectura del área (`test_design_system_guardrails`, `test_global_qss_ownership`, `test_theme_contrast`, las dos pruebas nuevas, `*_has_no_hardcoded_colors` de products/crm/assets, `test_bi_no_sql_in_ui`, `test_logistics_pwa_architecture`): 147 pasan y 2 fallan, las dos preexistentes (ver abajo).
- Módulos tocados: temas, gráficas, densidad, Apariencia, sesión, búsqueda, categorías, pantalla del cliente, POS visual, BI (`tests/unit/business_intelligence/`) y etiquetas QR de logística. Todo pasa, salvo lo preexistente.
- `tests/architecture` completo y `tests/ui` completo: **pendientes**. No se corrieron, como se pidió; `tests/ui` se cuelga (UI-001).

## Fallas preexistentes (no causadas por este lote)

- `tests/architecture/test_design_system_guardrails.py::test_desktop_visual_debt_does_not_grow` y `::test_visual_debt_baseline_is_exact_and_kept_pruned`:
  - Fallan igual en `HEAD` sin los cambios (comprobado con `git stash`) y figuran en `docs/sdlc/baseline/2026-10-28.md` como «`test_design_system_guardrails.py` (2)».
  - Son 17 hallazgos de `screen_without_explicit_overflow` / `native_operational_table` en configuracion, customers_crm, finance, meat_processing y pricing. Ninguno está en archivos de este lote.
  - La línea base corregida está en `sdlc/sdlc-ui-003-auto:pos_spj_v13.4/tests/architecture/design_system_debt_baseline.json` (UI-003) y no se duplicó aquí.
- `tests/integration/test_bi_caja_export_settings.py` (4 errores): falla al preparar el fixture, en `bi_seed.py:57` con «no such table: productos», que es una tabla legacy. No tiene relación con el PDF. No se volvió a correr en `HEAD`: no está verificado que sea preexistente, pero el error aparece al preparar los datos, antes de llegar al código de este lote.
