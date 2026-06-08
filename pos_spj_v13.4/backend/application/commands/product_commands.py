"""Product module commands."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class CreateProductCommand(BaseCommand):
    """Command for the canonical product creation route."""

    name: str = ""
    sku: str | None = None
    barcode: str = ""
    category: str = ""
    sale_price: float = 0.0
    purchase_price: float = 0.0
    minimum_sale_price: float = 0.0
    unit: str = ""
    sale_unit: str = ""
    purchase_unit: str = ""
    minimum_stock: float = 0.0
    product_type: str = "simple"
    image_path: str | None = None
    active: bool = True
    allow_duplicate_name: bool = False


@dataclass(frozen=True)
class UpdateProductCommand(CreateProductCommand):
    """Command for the canonical product update route."""

    product_id: int | str = 0
