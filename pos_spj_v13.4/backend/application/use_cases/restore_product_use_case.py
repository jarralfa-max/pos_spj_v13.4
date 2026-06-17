"""Use case for restoring soft-deleted products."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.services.product_catalog_service import ProductCatalogService


@dataclass(frozen=True)
class RestoreProductCommand:
    product_id: str
    operation_id: str
    user_name: str = ""


class RestoreProductUseCase:
    def __init__(self, catalog_service: ProductCatalogService) -> None:
        self._catalog_service = catalog_service

    def execute(self, command: RestoreProductCommand) -> dict:
        return self._catalog_service.restore_product(
            product_id=command.product_id,
            operation_id=command.operation_id,
            user_name=command.user_name,
        )
