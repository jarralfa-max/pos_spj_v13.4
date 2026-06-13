"""QueryServices for read-only UI/API data access."""

from backend.application.queries.base_query_service import (
    BaseQueryService,
    EmptyQueryDataSource,
    KpiMetric,
    QueryDataSource,
    QueryFilters,
    SearchResult,
    TableRow,
)
from backend.application.queries.customer_query_service import CustomerQueryService
from backend.application.queries.product_query_service import ProductQueryService
from backend.application.queries.supplier_query_service import SupplierQueryService
from backend.application.queries.employee_query_service import EmployeeQueryService
from backend.application.queries.branch_query_service import BranchQueryService
from backend.application.queries.driver_query_service import DriverQueryService
from backend.application.queries.asset_query_service import AssetQueryService
from backend.application.queries.delivery_query_service import DeliveryQueryService
from backend.application.queries.transfer_query_service import TransferQueryService
from backend.application.queries.waste_query_service import WasteQueryService
from backend.application.queries.production_query_service import ProductionQueryService
from backend.application.queries.quote_query_service import QuoteQueryService
from backend.application.queries.loyalty_query_service import LoyaltyQueryService
from backend.application.queries.cash_register_query_service import CashRegisterQueryService
from backend.application.queries.purchase_planning_query_service import PurchasePlanningQueryService
from backend.application.queries.business_intelligence_query_service import BusinessIntelligenceQueryService

__all__ = [
    "BaseQueryService",
    "EmptyQueryDataSource",
    "KpiMetric",
    "QueryDataSource",
    "QueryFilters",
    "SearchResult",
    "TableRow",
    "CustomerQueryService",
    "ProductQueryService",
    "SupplierQueryService",
    "EmployeeQueryService",
    "BranchQueryService",
    "DriverQueryService",
    "AssetQueryService",
    "DeliveryQueryService",
    "TransferQueryService",
    "WasteQueryService",
    "ProductionQueryService",
    "QuoteQueryService",
    "LoyaltyQueryService",
    "CashRegisterQueryService",
    "PurchasePlanningQueryService",
    "BusinessIntelligenceQueryService",
]
from backend.application.queries.hardware_settings_query_service import HardwareSettingsQueryService
from backend.application.queries.ticket_settings_query_service import TicketSettingsQueryService
