"""Reusable desktop UI components for the SPJ refactor."""

from frontend.desktop.components.address_input import AddressInput, AddressSuggestion
from frontend.desktop.components.asset_search_box import AssetSearchBox
from frontend.desktop.components.branch_search_box import BranchSearchBox
from frontend.desktop.components.customer_search_box import CustomerSearchBox
from frontend.desktop.components.date_range_filter import DateRange, DateRangeFilter
from frontend.desktop.components.driver_search_box import DriverSearchBox
from frontend.desktop.components.employee_search_box import EmployeeSearchBox
from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.components.numeric_input import NumericInput
from frontend.desktop.components.percent_input import PercentInput
from frontend.desktop.components.phone_input import PhoneInput
from frontend.desktop.components.product_search_box import ProductSearchBox
from frontend.desktop.components.quantity_input import QuantityInput
from frontend.desktop.components.search_selector import SearchOption, SearchSelector
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.status_badge import StatusBadge
from frontend.desktop.components.supplier_search_box import SupplierSearchBox
from frontend.desktop.components.tables import ColumnSpec, StandardTable
# ── DS-3/DS-4 canonical components ────────────────────────────────────────────
from frontend.desktop.components.icons import Icons, IconProvider, icon_accessible_name
from frontend.desktop.components.tooltip import apply_tooltip, build_tooltip_text
from frontend.desktop.components.buttons import (
    PrimaryButton, SecondaryButton, GhostButton, DangerButton, IconButton,
    create_danger_button,
    create_ghost_button,
    create_icon_button,
    create_outline_button,
    create_primary_button,
    create_secondary_button,
    create_success_button,
    create_table_action_button,
    create_warning_button,
)
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.cards import (
    AlertCard,
    ChartCard,
    InfoCard,
    SectionCard,
    StandardCard,
    SummaryCard,
)
from frontend.desktop.components.kpi_card import KPICard, KPIDTO, KPIState
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.view_states import (
    LoadingState, EmptyState, ErrorState, Toast,
    StateWidget,
    ViewState,
    create_state_widget,
)
from frontend.desktop.components.dialogs import (
    ConfirmationDialog,
    DestructiveConfirmationDialog,
    FormDialog,
    StandardDialog,
)
from frontend.desktop.components.time_input import TimeInput
from frontend.desktop.components.time_range_input import TimeRangeInput
# ── DS-4 specialized inputs ───────────────────────────────────────────────────
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.email_input import EmailInput
from frontend.desktop.components.tax_identifier_input import TaxIdentifierInput
from frontend.desktop.components.month_input import MonthInput
from frontend.desktop.components.duration_input import DurationInput
from frontend.desktop.components.date_input import DateInput, DateTimeInput
from frontend.desktop.components.text_inputs import (
    PasswordInput,
    StandardLineEdit,
    StandardTextArea,
)
from frontend.desktop.components.search_input import SearchInput
from frontend.desktop.components.barcode_input import BarcodeInput
from frontend.desktop.components.file_path_input import FilePathInput
from frontend.desktop.components.searchable_combo import SearchableComboBox
from frontend.desktop.components.entity_search_input import EntitySearchInput
from frontend.desktop.components.form_field import FieldState, FormField, StandardForm
# ── DS-5 charts ───────────────────────────────────────────────────────────────
from frontend.desktop.components.chart_view import HtmlChartView
from frontend.desktop.components.dashboard_grid import DashboardGrid
# ── FASE 6 worklist scaffold ────────────────────────────────────────────────
from frontend.desktop.components.worklist_page import WorklistPage
from frontend.desktop.components.branding import BrandAssetProvider, BrandLabel
from frontend.desktop.components.standard_window import StandardWindow
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.components.pages import (
    StandardPage, ScrollablePage, DashboardPage, FormPage, MasterDetailPage,
    SplitPage, TabbedPage, WizardPage, POSPage,
)
from frontend.desktop.components.tabs import TabBar, Tabs
from frontend.desktop.components.virtual_keyboard import KeyboardAwareInput, VirtualKeyboard
from frontend.desktop.components.selection_controls import StandardComboBox, StandardCheckBox, StandardRadioButton
from frontend.desktop.components.toolbar import Toolbar, FilterBar, ContextBar, Breadcrumbs
from frontend.desktop.components.weight_input import WeightInput

__all__ = [
    "LoadingState", "EmptyState", "ErrorState", "Toast",
    "IconProvider", "BrandAssetProvider", "BrandLabel", "StandardWindow",
    "PrimaryButton", "SecondaryButton", "GhostButton", "DangerButton", "IconButton",
    "PageViewport", "StandardPage", "ScrollablePage", "DashboardPage", "FormPage",
    "MasterDetailPage", "SplitPage", "TabbedPage", "WizardPage", "POSPage",
    "TabBar", "Tabs", "KeyboardAwareInput", "VirtualKeyboard", "WeightInput",
    "StandardComboBox", "StandardCheckBox", "StandardRadioButton",
    "Toolbar", "FilterBar", "ContextBar", "Breadcrumbs",
    "AddressInput",
    "AddressSuggestion",
    "AssetSearchBox",
    "BranchSearchBox",
    "CustomerSearchBox",
    "DateRange",
    "DateRangeFilter",
    "DriverSearchBox",
    "EmployeeSearchBox",
    "IntegerInput",
    "MoneyInput",
    "NumericInput",
    "PercentInput",
    "PhoneInput",
    "ProductSearchBox",
    "QuantityInput",
    "SearchOption",
    "SearchSelector",
    "SideNav",
    "StatusBadge",
    "SupplierSearchBox",
    "ColumnSpec",
    "StandardTable",
    # DS-3/DS-4 canonical components
    "Icons",
    "icon_accessible_name",
    "apply_tooltip",
    "build_tooltip_text",
    "create_primary_button",
    "create_secondary_button",
    "create_success_button",
    "create_warning_button",
    "create_danger_button",
    "create_outline_button",
    "create_ghost_button",
    "create_table_action_button",
    "create_icon_button",
    "PageHeader",
    "StandardCard",
    "SectionCard",
    "SummaryCard",
    "InfoCard",
    "AlertCard",
    "ChartCard",
    "KPICard",
    "KPIDTO",
    "KPIState",
    "KPIBar",
    "StateWidget",
    "ViewState",
    "create_state_widget",
    "StandardDialog",
    "ConfirmationDialog",
    "DestructiveConfirmationDialog",
    "FormDialog",
    "TimeInput",
    "TimeRangeInput",
    # DS-4 specialized inputs
    "DecimalInput",
    "EmailInput",
    "TaxIdentifierInput",
    "MonthInput",
    "DurationInput",
    "DateInput",
    "DateTimeInput",
    "StandardLineEdit",
    "StandardTextArea",
    "PasswordInput",
    "SearchInput",
    "BarcodeInput",
    "FilePathInput",
    "SearchableComboBox",
    "EntitySearchInput",
    "FormField",
    "StandardForm",
    "FieldState",
    # DS-5 charts
    "HtmlChartView",
    "DashboardGrid",
    "WorklistPage",
]
