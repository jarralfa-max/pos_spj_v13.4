"""Products module routes (§42) — page_id → lazy page factory.

Maps the declarative navigation page ids to the presentation-only page classes.
Lazy imports keep Qt out of import time for the non-UI (tested) layers. Pages not
yet built fall back to None (the shell shows a placeholder).
"""

from __future__ import annotations


def build_page(page_id: str, presenter):
    if page_id == "products_overview":
        from frontend.desktop.modules.products.pages.overview_page import (
            ProductsOverviewPage,
        )
        return ProductsOverviewPage(presenter)
    if page_id == "products_catalog":
        from frontend.desktop.modules.products.pages.product_catalog_page import (
            ProductCatalogPage,
        )
        return ProductCatalogPage(presenter)
    return None
