"""ProviderRegistry — maps a provider type to its adapter (§15).

Adapters register themselves by ``provider_type``; the gateway looks them up. No
adapter registered → the gateway raises UnknownCatalogProviderError.
"""

from __future__ import annotations

from backend.domain.products.external_enums import ExternalProviderType


class ProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[ExternalProviderType, object] = {}

    def register(self, adapter) -> None:
        self._adapters[adapter.provider_type] = adapter

    def get(self, provider_type: ExternalProviderType):
        return self._adapters.get(provider_type)

    def providers(self) -> list[ExternalProviderType]:
        return list(self._adapters)
