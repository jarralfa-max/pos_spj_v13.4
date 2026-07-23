"""Shelf-life policy (§19, §35) — a perishable product needs a shelf-life profile.

Fuels the "producto perecedero sin vida útil" alert and blocks activation when a
perishable/expiration-controlled product lacks its shelf-life profile.
"""

from __future__ import annotations

from backend.domain.products.entities.product import Product
from backend.domain.products.exceptions import ShelfLifeRequiredError


def is_perishable(product: Product) -> bool:
    return product.expiration_controlled


def require_shelf_life(product: Product, *, has_shelf_life_profile: bool) -> None:
    if is_perishable(product) and not has_shelf_life_profile:
        raise ShelfLifeRequiredError(
            "Un producto con caducidad requiere perfil de vida útil (§19)")
