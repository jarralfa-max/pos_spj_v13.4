"""Reusable desktop UI components for the SPJ refactor."""

from frontend.desktop.components.address_input import AddressInput, AddressSuggestion
from frontend.desktop.components.asset_search_box import AssetSearchBox
from frontend.desktop.components.branch_search_box import BranchSearchBox
from frontend.desktop.components.customer_search_box import CustomerSearchBox
from frontend.desktop.components.date_range_filter import DateRange, DateRangeFilter
from frontend.desktop.components.driver_search_box import DriverSearchBox
from frontend.desktop.components.debounced_search_input import DebouncedSearchInput
from frontend.desktop.components.empty_state import EmptyState
from frontend.desktop.components.loading_state import LoadingState
from frontend.desktop.components.pagination_bar import PaginationBar
from frontend.desktop.components.employee_search_box import EmployeeSearchBox
from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.components.numeric_input import NumericInput
from frontend.desktop.components.percent_input import PercentInput
from frontend.desktop.components.phone_input import PhoneInput
from frontend.desktop.components.product_search_box import ProductSearchBox
from frontend.desktop.components.quantity_input import QuantityInput
from frontend.desktop.components.search_selector import SearchOption, SearchSelector
from frontend.desktop.components.status_badge import StatusBadge
from frontend.desktop.components.supplier_search_box import SupplierSearchBox

__all__ = [
    "AddressInput",
    "AddressSuggestion",
    "DebouncedSearchInput",
    "EmptyState",
    "LoadingState",
    "PaginationBar",
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
    "StatusBadge",
    "SupplierSearchBox",
]
