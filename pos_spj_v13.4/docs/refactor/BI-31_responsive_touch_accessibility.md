# BI-31 — Responsive / Touch / Accessibility

Estado: **DONE** (auditoría + correcciones reales encontradas)

## Alcance

§14/§89-90/§107-108 (aprox.): confirmar que el módulo nuevo
(`frontend/desktop/modules/business_intelligence/`, BI-23..30) cumple los
mismos estándares responsive/touch/accesibilidad que el resto del Design
System, y corregir lo que no cumpla.

## Metodología

Auditoría archivo por archivo de las 10 páginas reales (BI-24..30) y los
widgets de navegación (BI-23) contra 3 ejes:

1. **Responsive**: ¿el layout reflowa con el ancho de la ventana, o hay
   anchos/altos fijos que lo rompen?
2. **Touch**: ¿los controles interactivos (botones, inputs, filas de tabla)
   cumplen el mínimo táctil de 40px (`TouchTarget`, `frontend/desktop/
   themes/tokens.py`)?
3. **Accessibility**: ¿cada página expone un nombre/descripción accesible
   (lector de pantalla) y cada control tiene tooltip/nombre accesible?

## Hallazgos y correcciones

| Eje | Hallazgo | Corrección |
|---|---|---|
| Accesibilidad | Las 7 páginas reales nuevas (BI-24..30) **no** llamaban `setAccessibleName()`/`setAccessibleDescription()` a nivel de página — a diferencia de la plantilla original (`OrdersAnalyticsPage`), que sí lo hace. `BusinessIntelligencePlaceholderPage` (BI-23) sí lo hacía; las páginas reales, no. | Se agregó `setAccessibleName`/`setAccessibleDescription` a las 7 páginas, con el mismo patrón `"Inteligencia de Negocios — {título}"` que usa el placeholder. Protegido por `test_every_real_page_declares_an_accessible_name_and_description`. |
| Touch | `ReportsPage` (BI-30) usaba `QComboBox` crudo sin altura mínima táctil — a diferencia de `IntegerInput`/`NumericInput`/`PercentInput`/`StandardLineEdit`, que ya fijan `TouchTarget.INPUT_HEIGHT` en su propio constructor. | Se agregó `setMinimumHeight(TouchTarget.MIN_HEIGHT)` + `setAccessibleName` a ambos combos (reporte/formato). |
| Touch/Responsive | Botones, `KPIBar`, `StandardTable`, `IntegerInput`/`NumericInput`/`PercentInput`/`StandardLineEdit`, `ProductSearchBox`/`BranchSearchBox` | **Ya conformes** — cada uno ya centraliza su propio cumplimiento (`create_*_button` fija altura+nombre accesible; `KPIBar._columns()` recalcula columnas en `resizeEvent`; `StandardTable` usa `TableMetrics`/`TouchTarget` en su constructor). No se tocó nada — confirmar que ya es así es el propósito de esta auditoría, no una excusa para reescribir código que ya cumple. |
| Responsive | Un único `setFixedWidth` encontrado en todo el módulo, en `business_intelligence_sidebar_widget.py` (rail de icono colapsado). | **No es una violación** — es el mismo patrón responsive deliberado que `orders_delivery` ya estableció (ancho fijo angosto solo en el estado colapsado, ancho flexible en el expandido). Documentado como excepción explícita en el guardrail, no descubierto por accidente. |

## Hallazgo repo-wide NO corregido en esta fase (fuera del alcance del módulo BI)

`frontend/desktop/components/search_selector.py` (`SearchSelector`, base de
`ProductSearchBox`/`BranchSearchBox`, usado también por `losses` y
`orders_delivery`) no fija una altura táctil mínima en su `QLineEdit`
interno — a diferencia de `IntegerInput`/`NumericInput`/etc. Es un hallazgo
real, pero corregir un componente compartido fuera de la responsabilidad
declarada de esta transformación (`frontend/desktop/modules/
business_intelligence/`) requeriría validar contra los tests de `losses`/
`orders_delivery` también, que está fuera del alcance de esta pasada.
Documentado para una futura pasada de endurecimiento del Design System, no
ignorado.

## Auditoría REGLA CERO

Sin identidad — cambios puramente de presentación/accesibilidad. N/A.

## Tests

`tests/architecture/test_business_intelligence_responsive_touch_accessibility.py`
(3 guardrails nuevos): las 10 páginas reales declaran nombre+descripción
accesible (instanciación real de Qt vía `build_page()`), ningún
`QPushButton(` crudo fuera de las fábricas canónicas, y ningún
`setFixedWidth`/`setFixedHeight` fuera de la excepción documentada del rail
colapsado. **119 tests verdes** en el paquete `business_intelligence` +
guardrails (109 previos + 10 de BI-30, sin nuevos tests unitarios en esta
fase — los cambios son correcciones directas verificadas por los 3
guardrails nuevos).

## Pendiente

- El hallazgo de `SearchSelector` (altura táctil) queda documentado para una
  futura pasada de Design System, no de esta transformación BI.
- BI-32 audita candidatos de eliminación de legacy confirmados sin
  consumidores reales.
