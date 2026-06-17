"""Product module commands."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.commands.base_command import BaseCommand


@dataclass(frozen=True)
class CreateProductCommand(BaseCommand):
    name: str = ""
    sku: str | None = None
    barcode: str = ""
    category: str = ""
    sale_price: float = 0.0
    purchase_price: float = 0.0
    minimum_sale_price: float = 0.0
    unit: str = "pza"
    sale_unit: str | None = None
    purchase_unit: str | None = None
    minimum_stock: float = 0.0
    product_type: str = "simple"
    is_composite: bool = False
    is_byproduct: bool = False
    image_path: str | None = None
    active: bool = True
    allow_duplicate_name: bool = False


@dataclass(frozen=True)
class UpdateProductCommand(CreateProductCommand):
    product_id: str = ""
