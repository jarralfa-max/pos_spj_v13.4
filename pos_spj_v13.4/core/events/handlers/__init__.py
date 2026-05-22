# core/events/handlers — Phase 1 + Phase 3 + Phase 4 + Phase 5 + Phase 6 + Phase 7 domain event handlers
from core.events.handlers.inventory_handler import SaleInventoryHandler
from core.events.handlers.finance_handler import SaleFinanceHandler
from core.events.handlers.production_handler import ProductionInventoryHandler
from core.events.handlers.purchase_handler import PurchaseInventoryHandler, PurchaseFinanceHandler
from core.events.handlers.transfer_handler import TransferInventoryHandler
from core.events.handlers.financial_trace_handler import (
    SaleTraceHandler,
    PurchaseTraceHandler,
    PaymentTraceHandler,
    PayrollTraceHandler,
    WasteTraceHandler,
    LoyaltyTraceHandler,
    DeliveryPaymentHandler,
    DriverSettlementHandler,
    MaintenanceTraceHandler,
    SupplyTraceHandler,
)

__all__ = [
    "SaleInventoryHandler",
    "SaleFinanceHandler",
    "ProductionInventoryHandler",
    "PurchaseInventoryHandler",
    "PurchaseFinanceHandler",
    "TransferInventoryHandler",
    # Trazabilidad financiera end-to-end (migración 083)
    "SaleTraceHandler",
    "PurchaseTraceHandler",
    "PaymentTraceHandler",
    "PayrollTraceHandler",
    "WasteTraceHandler",
    "LoyaltyTraceHandler",
    "DeliveryPaymentHandler",
    "DriverSettlementHandler",
    "MaintenanceTraceHandler",
    "SupplyTraceHandler",
]
