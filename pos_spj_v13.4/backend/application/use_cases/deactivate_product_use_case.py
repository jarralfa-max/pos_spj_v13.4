"""Use case for product soft-delete."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.services.product_catalog_service import ProductCatalogService


@dataclass(frozen=True)
class DeactivateProductCommand:
    product_id: str
    operation_id: str
    user_name: str = ""


class DeactivateProductUseCase:
    def __init__(self, catalog_service: ProductCatalogService) -> None:
        self._catalog_service = catalog_service

    def execute(self, command: DeactivateProductCommand) -> dict:
        return self._catalog_service.deactivate_product(
            product_id=command.product_id,
            operation_id=command.operation_id,
            user_name=command.user_name,
        )
