# Plantilla obligatoria de migración UI/UX por módulo (FASE DS-10)

> Todo módulo que se refactorice después del Design System debe seguir esta
> plantilla. **El estándar no nace dentro del módulo; el módulo nace dentro del
> estándar.** No se marca un módulo como `MIGRATED` si crea componentes visuales
> fuera del estándar global.

## 0. Regla de oro

```
Componentes oficiales → Tokens oficiales → QSS global → ThemeManager → Tema
```

Imports permitidos en la UI del módulo:

```python
from frontend.desktop.components import (
    PageHeader, KPICard, KPIDTO, KPIBar, StandardCard, SectionCard,
    StandardTable, ColumnSpec, StandardDialog, ConfirmationDialog,
    create_primary_button, create_secondary_button, create_danger_button,
    create_icon_button, apply_tooltip, Icons, StatusBadge,
    TimeInput, TimeRangeInput, PhoneInput, MoneyInput, PercentInput,
    IntegerInput, create_state_widget, ViewState,
)
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import Spacing, TableMetrics  # números visuales
from frontend.desktop.formatters import format_money, format_date, format_time
```

Prohibido en la UI del módulo:

```python
import sqlite3
from core.db... import ...
from repositories... import ...
conn.execute(...); cursor.execute(...); commit(); rollback()
widget.setStyleSheet("color: ...")     # estilos inline
"#1F3B2E"                              # colores literales
QChart / matplotlib / pyqtgraph        # gráficas nativas
```

## 1. Auditoría por módulo (llenar antes de tocar código)

| Aspecto | ¿Cómo está hoy? | Acción |
|---|---|---|
| PageHeader | | usar `PageHeader` |
| KPIs | | `KPIDTO` + `KPICard`/`KPIBar` (cálculo en QueryService) |
| Cards | | `StandardCard`/`SectionCard`/… |
| Charts | | `ChartDataDTO` + `HtmlChartView` (ECharts) |
| Tablas | | `StandardTable` + `ColumnSpec` |
| Filtros | | `FilterBar` (o `DateRangeFilter`) |
| Dialogs | | `StandardDialog`/`FormDialog`/`ConfirmationDialog` |
| Inputs | | matriz canónica (ver §3) |
| Tooltips | | `apply_tooltip` |
| Estados | | `create_state_widget(ViewState.*)` |
| Formatters | | `frontend.desktop.formatters` |
| Iconos | | `Icons.*` (sin emojis) |
| Responsive | | validar 1366×768 / 1440×900 / 1920×1080 |
| Accesibilidad | | accessibleName/Description, foco, teclado |
| Tema | | claro y oscuro |

## 2. Estructura objetivo del módulo

```
frontend/desktop/modules/<module>/
  <module>_view.py        # navegación + páginas (solo UI)
  <module>_presenter.py   # orquestación ligera; llama QueryServices/UseCases
  <module>_view_models.py # strings listos para mostrar (usa formatters)
  <module>_routes.py      # composition root (único que ve la conexión)
  pages/                  # una página por sección, hereda de un _page_base
  dialogs/                # formularios sobre StandardDialog/FormDialog
backend/application/queries/<module>/   # lecturas para UI (DTOs)
backend/application/use_cases/<module>/ # mutaciones
```

## 3. Matriz de inputs canónicos (obligatoria)

```
Teléfono → PhoneInput (PhoneWidget)      Dirección → AddressInput (geocoding)
Dinero → MoneyInput (Decimal)            Porcentaje → PercentInput (Decimal)
Entero → IntegerInput                    Cantidad+unidad → QuantityInput
Hora → TimeInput (HH:mm)                 Rango horario → TimeRangeInput
Catálogo chico → SearchableComboBox      Entidad grande → EntitySearchInput
```

Prohibido `QLineEdit` para estos datos especializados.

## 4. Checklist de aceptación (Definition of Done)

```
[ ] UI en frontend/desktop/modules/<module>/, sin lógica en modulos/.
[ ] PageHeader canónico.
[ ] KPIs vía KPIDTO/KPICard (sin cálculo en el widget).
[ ] Tablas vía StandardTable.
[ ] Diálogos vía StandardDialog/FormDialog.
[ ] Inputs especializados según la matriz.
[ ] Tooltips vía apply_tooltip.
[ ] Estados de vista (loading/empty/error/…).
[ ] Formatters compartidos (sin f"${...}").
[ ] Iconos vía Icons (sin emojis).
[ ] Sin SQL / commit / rollback en UI.
[ ] Sin colores literales ni setStyleSheet con color.
[ ] Sin gráficas PyQt nativas (HTML+JS/ECharts).
[ ] Tema claro y oscuro validados.
[ ] Responsive 1366×768.
[ ] Accesibilidad (nombres, foco, teclado).
[ ] Pasa tests/architecture (guardrails DS-8) y tests/ui de sus componentes.
[ ] Registrado en docs/refactor/module_relocation_map.md.
```

Un módulo se marca `MIGRATED` solo cuando cumple todo lo anterior.
