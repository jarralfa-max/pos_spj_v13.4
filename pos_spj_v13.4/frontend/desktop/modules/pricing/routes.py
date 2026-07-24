"""Pricing module routes (PRC-7) — page_id → lazy page factory.

Maps navigation page ids to presentation-only page classes. Lazy imports keep Qt
out of import time for the non-UI (tested) layers. Pages not yet built fall back to
None (the shell shows a placeholder).
"""

from __future__ import annotations


def build_page(page_id: str, presenter):
    if page_id == "pricing_overview":
        from frontend.desktop.modules.pricing.pages.overview_page import PricingOverviewPage
        return PricingOverviewPage(presenter)
    if page_id == "pricing_lists":
        from frontend.desktop.modules.pricing.pages.price_lists_page import PriceListsPage
        return PriceListsPage(presenter)
    if page_id == "pricing_prices":
        from frontend.desktop.modules.pricing.pages.product_prices_page import (
            ProductPricesPage,
        )
        return ProductPricesPage(presenter)
    if page_id == "pricing_costs":
        from frontend.desktop.modules.pricing.pages.costs_page import CostsPage
        return CostsPage(presenter)
    if page_id == "pricing_history":
        from frontend.desktop.modules.pricing.pages.history_page import PriceHistoryPage
        return PriceHistoryPage(presenter)
    return None
