# Guía de migración al Design System

Ver la plantilla operativa completa en
`docs/refactor/module_ui_ux_migration_template.md`. Resumen:

1. **Auditar** el módulo (header, KPIs, cards, charts, tablas, filtros, dialogs,
   inputs, tooltips, estados, formatters, iconos, responsive, accesibilidad, tema).
2. **Reubicar** la UI a `frontend/desktop/modules/<module>/` (view/presenter/
   routes/pages/dialogs). Lecturas → QueryService; mutaciones → UseCase.
3. **Reemplazar** primitivos locales por los canónicos
   (`frontend.desktop.components`), tokens (`frontend.desktop.themes`) y formatters
   (`frontend.desktop.formatters`).
4. **Eliminar** estilos inline, colores literales, KPIs/cards/headers locales,
   gráficas PyQt nativas y `QLineEdit` para datos especializados.
5. **Validar** con los guardrails DS-8 (`tests/architecture/test_design_system_guardrails.py`,
   `test_theme_contrast.py`) y los tests de componentes (`tests/ui/`).
6. **Registrar** el módulo en `docs/refactor/module_relocation_map.md` y marcar
   `MIGRATED` solo cuando cumpla el checklist.

## Componentes disponibles hoy

- Layout: `PageHeader`, `SectionCard`/`StandardCard`/`SummaryCard`/`InfoCard`/
  `AlertCard`/`ChartCard`, `StandardTable`.
- Datos: `KPICard`/`KPIBar` (DTO), `StatusBadge`, `create_state_widget`.
- Acciones: factories de botones, `create_icon_button`, `apply_tooltip`, `Icons`.
- Diálogos: `StandardDialog`/`ConfirmationDialog`/`DestructiveConfirmationDialog`/
  `FormDialog`.
- Inputs: `TimeInput`, `TimeRangeInput`, `PhoneInput`, `MoneyInput`,
  `PercentInput`, `IntegerInput`, `AddressInput`.
- Formatters: `format_money/quantity/percentage/date/time/duration/phone/address/status`.

## Pendiente de crear (siguiente iteración del DS)

Inputs: `EmailInput`, `TaxIdentifierInput`, `DecimalInput`, `MonthInput`,
`DurationInput`, `SearchInput`, `SearchableComboBox`, `EntitySearchInput`,
`BarcodeInput`, `PasswordInput`, `FilePathInput`, `DateInput`/`DateTimeInput`.
Charts: `ChartDataDTO`, `HtmlChartView` (ECharts), `ChartCard`, `DashboardGrid`.
`FilterBar`/`Toolbar`, `StandardForm`/`FormField`. Migración piloto de Configuración.
