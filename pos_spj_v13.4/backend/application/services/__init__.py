"""Application services for canonical module routes."""

from backend.application.services.sales_application_service import SalesApplicationService
from backend.application.services.waste_application_service import WasteApplicationService, WasteFinanceHandler

from backend.application.services.cash_register_application_service import (
    CashRegisterApplicationService,
)

__all__ = [
    "SalesApplicationService", "WasteApplicationService", "WasteFinanceHandler",
    "CashRegisterApplicationService",
]
from backend.application.services.product_catalog_service import ProductCatalogService
from backend.application.services.product_image_service import ProductImageService
