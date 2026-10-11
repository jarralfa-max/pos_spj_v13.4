"""Canonical application use case shells."""

from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.base_use_case import DelegatingUseCase
from backend.application.use_cases.execute_meat_production_use_case import ExecuteMeatProductionUseCase
from backend.application.use_cases.create_delivery_order_use_case import CreateDeliveryOrderUseCase
from backend.application.use_cases.convert_quote_to_sale_use_case import ConvertQuoteToSaleUseCase
from backend.application.use_cases.generate_purchase_plan_use_case import GeneratePurchasePlanUseCase

__all__ = [
    "BaseUseCase",
    "DelegatingUseCase",
    "ExecuteMeatProductionUseCase",
    "CreateDeliveryOrderUseCase",
    "ConvertQuoteToSaleUseCase",
    "GeneratePurchasePlanUseCase",
]
