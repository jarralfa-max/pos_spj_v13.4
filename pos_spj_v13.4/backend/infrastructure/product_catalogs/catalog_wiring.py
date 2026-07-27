"""Catalog wiring (§15) — assemble adapters with their real clients.

Keeps composition out of the adapters themselves: the app wires a live
:class:`OpenFoodFactsHttpClient` into the :class:`OpenFoodFactsAdapter`, while
tests can inject a fake client. ``build_default_registry`` returns a
:class:`ProviderRegistry` with the Open Food Facts provider ready to use.
"""

from __future__ import annotations

from typing import Optional

from backend.infrastructure.product_catalogs.open_food_facts_adapter import (
    OpenFoodFactsAdapter,
    RawCatalogClient,
)
from backend.infrastructure.product_catalogs.open_food_facts_http_client import (
    OpenFoodFactsHttpClient,
)
from backend.infrastructure.product_catalogs.provider_registry import ProviderRegistry


def build_open_food_facts_adapter(
        client: Optional[RawCatalogClient] = None) -> OpenFoodFactsAdapter:
    """Build the OFF adapter over a live HTTP client (or an injected fake)."""
    return OpenFoodFactsAdapter(client or OpenFoodFactsHttpClient())


def build_default_registry(
        off_client: Optional[RawCatalogClient] = None) -> ProviderRegistry:
    """Registry with Open Food Facts registered against a real HTTP client."""
    registry = ProviderRegistry()
    registry.register(build_open_food_facts_adapter(off_client))
    return registry
