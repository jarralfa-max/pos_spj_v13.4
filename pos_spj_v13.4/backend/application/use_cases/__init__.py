"""Canonical application use case shells."""

from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.base_use_case import DelegatingUseCase
from backend.application.use_cases.register_waste_use_case import RegisterWasteUseCase
from backend.application.use_cases.create_sale_use_case import CreateSaleUseCase
from backend.application.use_cases.execute_meat_production_use_case import ExecuteMeatProductionUseCase
from backend.application.use_cases.dispatch_transfer_use_case import DispatchTransferUseCase
from backend.application.use_cases.receive_transfer_use_case import ReceiveTransferUseCase
from backend.application.use_cases.create_delivery_order_use_case import CreateDeliveryOrderUseCase
from backend.application.use_cases.create_product_use_case import CreateProductUseCase
from backend.application.use_cases.update_product_use_case import UpdateProductUseCase
from backend.application.use_cases.generate_z_cut_use_case import GenerateZCutUseCase
from backend.application.use_cases.convert_quote_to_sale_use_case import ConvertQuoteToSaleUseCase
from backend.application.use_cases.generate_purchase_plan_use_case import GeneratePurchasePlanUseCase

__all__ = [
    "BaseUseCase",
    "DelegatingUseCase",
    "RegisterWasteUseCase",
    "CreateSaleUseCase",
    "ExecuteMeatProductionUseCase",
    "DispatchTransferUseCase",
    "ReceiveTransferUseCase",
    "CreateDeliveryOrderUseCase",
    "CreateProductUseCase",
    "UpdateProductUseCase",
    "GenerateZCutUseCase",
    "ConvertQuoteToSaleUseCase",
    "GeneratePurchasePlanUseCase",
]
from backend.application.use_cases.deactivate_product_use_case import DeactivateProductUseCase
from backend.application.use_cases.restore_product_use_case import RestoreProductUseCase
from backend.application.use_cases.create_customer_use_case import CreateCustomerUseCase
from backend.application.use_cases.update_product_use_case import UpdateProductUseCase
