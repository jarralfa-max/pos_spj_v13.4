# Punto 2 — Paleta JUANIS

Estado: **COMPLETADO**. Verificación: 2026-09-12.
Alcance: paleta canónica y referencias de sus escalas.

| Ancla | Color oficial |
|---|---|
| `FOREST_GREEN` | `#18372B` — Verde profundo |
| `WHITE` | `#FFFFFF` — Blanco |
| `PREMIUM_GOLD` | `#C6A15B` — Dorado cálido |
| `TRADITIONAL_RED` | `#9D2927` — Rojo profundo |
| `CHARCOAL` | `#252825` — Carbón |
| `WARM_WHITE` | `#F8F8F5` — Blanco cálido |

Los seis valores ya coincidían con el documento solicitado. Se retiraron los
alias históricos `SOFT_CREAM` y `EARTH_BROWN`; las escalas `CREAM_*` y `BROWN_*`
se sustituyeron por `WARM_WHITE_*` y `CHARCOAL_*`. Sus consumidores se limitaban
a la capa de temas y se actualizaron juntos. No se añadieron colores de marca.

Archivos modificados: `frontend/desktop/themes/brand_palette.py`,
`semantic_colors.py` y `frontend/desktop/design_system/visual_guidelines.md`.
Archivo creado: este informe. Archivos eliminados: ninguno.

Validación antes/después: **62 PASSED, 0 FAILED, 0 SKIPPED** en
`tests/architecture/test_theme_contrast.py` y `tests/ui/test_theme_density_icons.py`.
Además, se compararon todos los valores semánticos de Claro/Oscuro, las paletas de
gráficas y las seis salidas QSS (dos temas × tres densidades): son idénticos a los
anteriores. Las capturas de la fase anterior siguen representando estos colores.
No se modificaron reglas de negocio ni se añadieron tests para el cambio de nombres.

Las variantes semánticas accesibles pueden diferir de las anclas, especialmente
en Oscuro. La incorporación de logos oficiales pertenece al punto 6,
`BrandAssetProvider`, y no cambia el cierre de esta paleta.

El resultado global de suites y la adopción pendiente del resto del sistema
permanecen documentados en [la auditoría general](global_ui_ux_design_system_audit.md).
Siguiente punto del orden solicitado: **3. Light / Dark**.
