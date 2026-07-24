"""Product alert detectors (§35) — pure functions that surface data-quality alerts.

Given a product and a few presence flags (which profiles/configs exist), returns
the list of ``ProductAlertType`` that currently apply. No persistence, no I/O; the
notification service turns these into deliveries.
"""

from __future__ import annotations

from backend.domain.products.entities.product import Product
from backend.domain.products.enums import LifecycleStatus
from backend.domain.products.notification_enums import ProductAlertType


def detect_product_alerts(
    product: Product,
    *,
    has_shelf_life_profile: bool = False,
    has_quality_profile: bool = False,
    catch_weight_configured: bool = False,
    lot_configured: bool = True,
) -> list[ProductAlertType]:
    alerts: list[ProductAlertType] = []

    if product.missing_activation_data():
        alerts.append(ProductAlertType.PRODUCT_INCOMPLETE)

    if product.is_meat and not product.species_id:
        alerts.append(ProductAlertType.MEAT_WITHOUT_SPECIES)

    if product.expiration_controlled and not has_shelf_life_profile:
        alerts.append(ProductAlertType.PERISHABLE_WITHOUT_SHELF_LIFE)

    if product.catch_weight_enabled and not catch_weight_configured:
        alerts.append(ProductAlertType.CATCH_WEIGHT_WITHOUT_RANGE)

    if product.lot_controlled and not lot_configured:
        alerts.append(ProductAlertType.LOT_REQUIRED_NOT_CONFIGURED)

    if product.is_meat and product.quality_controlled and not has_quality_profile:
        alerts.append(ProductAlertType.MEAT_WITHOUT_QUALITY_PROFILE)

    if product.lifecycle_status is LifecycleStatus.UNDER_REVIEW:
        alerts.append(ProductAlertType.PENDING_APPROVAL)

    return alerts


def detect_discontinued_still_active(
    product: Product, *, enabled_branch_count: int
) -> ProductAlertType | None:
    """A discontinued product still enabled in branches is an inconsistency (§35)."""
    if product.lifecycle_status is LifecycleStatus.DISCONTINUED and enabled_branch_count > 0:
        return ProductAlertType.DISCONTINUED_STILL_ACTIVE
    return None
