"""Machine-readable registry of canonical components (FASE DS-7).

Single source of truth for *which* components are official, where they live,
their variants and states. Guardrail/catalog tests consume this so the standard
can't silently drift. Adding a component means registering it here.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ComponentContract:
    name: str
    module: str            # import path
    symbol: str            # attribute name in the module
    purpose: str
    variants: tuple[str, ...] = ()
    states: tuple[str, ...] = ()


_BUTTON_VARIANTS = ("primary", "secondary", "success", "warning", "danger",
                    "outline", "ghost", "table_action", "icon")
_CARD_VARIANTS = ("standard", "section", "summary", "info", "alert", "chart")
_KPI_VARIANTS = ("neutral", "primary", "success", "warning", "danger", "info", "accent")
_KPI_STATES = ("LOADING", "READY", "EMPTY", "STALE", "ERROR", "NO_PERMISSION",
               "OFFLINE", "PARTIAL_DATA")
_VIEW_STATES = ("LOADING", "READY", "EMPTY", "ERROR", "NO_PERMISSION", "OFFLINE",
                "STALE", "PARTIAL_DATA")
_BADGE_VARIANTS = ("neutral", "info", "success", "warning", "danger", "accent")

CONTRACTS: tuple[ComponentContract, ...] = (
    ComponentContract("PageHeader", "frontend.desktop.components.page_header",
                      "PageHeader", "Encabezado canónico de página."),
    ComponentContract("KPICard", "frontend.desktop.components.kpi_card", "KPICard",
                      "KPI dirigido por DTO (solo presentación).",
                      variants=_KPI_VARIANTS, states=_KPI_STATES),
    ComponentContract("KPIBar", "frontend.desktop.components.kpi_bar", "KPIBar",
                      "Fila/grid responsivo de KPICards."),
    ComponentContract("StandardCard", "frontend.desktop.components.cards",
                      "StandardCard", "Contenedor base.", variants=_CARD_VARIANTS),
    ComponentContract("SectionCard", "frontend.desktop.components.cards",
                      "SectionCard", "Agrupación con título."),
    ComponentContract("StandardTable", "frontend.desktop.components.tables",
                      "StandardTable", "Tabla con política visual única."),
    ComponentContract("StandardDialog", "frontend.desktop.components.dialogs",
                      "StandardDialog", "Diálogo base."),
    ComponentContract("ConfirmationDialog", "frontend.desktop.components.dialogs",
                      "ConfirmationDialog", "Confirmación estándar."),
    ComponentContract("StatusBadge", "frontend.desktop.components.status_badge",
                      "StatusBadge", "Insignia de estado.", variants=_BADGE_VARIANTS),
    ComponentContract("StateWidget", "frontend.desktop.components.view_states",
                      "StateWidget", "Estados de vista.", states=_VIEW_STATES),
    ComponentContract("TimeInput", "frontend.desktop.components.time_input",
                      "TimeInput", "Hora 24h HH:mm."),
    ComponentContract("TimeRangeInput", "frontend.desktop.components.time_range_input",
                      "TimeRangeInput", "Rango horario con regla nocturna explícita."),
    ComponentContract("PhoneInput", "frontend.desktop.components.phone_input",
                      "PhoneInput", "Teléfono E.164 (PhoneWidget)."),
    ComponentContract("MoneyInput", "frontend.desktop.components.money_input",
                      "MoneyInput", "Dinero Decimal + moneda."),
    ComponentContract("PercentInput", "frontend.desktop.components.percent_input",
                      "PercentInput", "Porcentaje Decimal."),
    ComponentContract("IntegerInput", "frontend.desktop.components.integer_input",
                      "IntegerInput", "Entero."),
    ComponentContract("AddressInput", "frontend.desktop.components.address_input",
                      "AddressInput", "Dirección con geocoding + captura manual."),
    ComponentContract("DecimalInput", "frontend.desktop.components.decimal_input",
                      "DecimalInput", "Decimal exacto (nunca float)."),
    ComponentContract("EmailInput", "frontend.desktop.components.email_input",
                      "EmailInput", "Correo con validación + normalización segura."),
    ComponentContract("TaxIdentifierInput",
                      "frontend.desktop.components.tax_identifier_input",
                      "TaxIdentifierInput", "RFC/CURP/VAT normalizado y validado."),
    ComponentContract("MonthInput", "frontend.desktop.components.month_input",
                      "MonthInput", "Periodo mensual yyyy-MM."),
    ComponentContract("DurationInput", "frontend.desktop.components.duration_input",
                      "DurationInput", "Duración (amount+unidad) → minutos."),
    ComponentContract("DateInput", "frontend.desktop.components.date_input",
                      "DateInput", "Fecha dd/MM/yyyy."),
    ComponentContract("DateTimeInput", "frontend.desktop.components.date_input",
                      "DateTimeInput", "Fecha y hora dd/MM/yyyy HH:mm."),
    ComponentContract("SearchInput", "frontend.desktop.components.search_input",
                      "SearchInput", "Búsqueda con debounce (solo señales)."),
    ComponentContract("SearchableComboBox",
                      "frontend.desktop.components.searchable_combo",
                      "SearchableComboBox", "Catálogo pequeño con filtro por contenido."),
    ComponentContract("EntitySearchInput",
                      "frontend.desktop.components.entity_search_input",
                      "EntitySearchInput", "Entidad grande: búsqueda paginada por UUID."),
    ComponentContract("BarcodeInput", "frontend.desktop.components.barcode_input",
                      "BarcodeInput", "Lector HID; Enter no envía el formulario."),
    ComponentContract("PasswordInput", "frontend.desktop.components.text_inputs",
                      "PasswordInput", "Contraseña con revelar opcional."),
    ComponentContract("FilePathInput", "frontend.desktop.components.file_path_input",
                      "FilePathInput", "Ruta de archivo (solo lectura + examinar)."),
    ComponentContract("FormField", "frontend.desktop.components.form_field",
                      "FormField", "label + input + helper + error + tooltip."),
    ComponentContract("StandardForm", "frontend.desktop.components.form_field",
                      "StandardForm", "Formulario con validación inline."),
    ComponentContract("HtmlChartView", "frontend.desktop.components.chart_view",
                      "HtmlChartView", "Gráfica HTML+JS (ECharts) desde ChartDataDTO."),
    ComponentContract("ChartCard", "frontend.desktop.components.cards", "ChartCard",
                      "Contenedor de gráfica."),
    ComponentContract("DashboardGrid", "frontend.desktop.components.dashboard_grid",
                      "DashboardGrid", "Layout de dashboard con pesos."),
)

BUTTON_FACTORIES: tuple[str, ...] = (
    "create_primary_button", "create_secondary_button", "create_success_button",
    "create_warning_button", "create_danger_button", "create_outline_button",
    "create_ghost_button", "create_table_action_button", "create_icon_button",
)


def contract_names() -> tuple[str, ...]:
    return tuple(c.name for c in CONTRACTS)
