"""External product catalog gateway + adapter port (§15).

An ``ExternalCatalogAdapter`` (Protocol) fetches raw records from one provider and
returns them as canonical dicts (external_id, name, barcode, brand, category,
net_weight, unit, raw_payload). The gateway dispatches a search to the adapter
registered for a source's provider and turns the raw dicts into
``ExternalProductRecord`` domain objects (carrying provenance = source id).
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.products.entities.external_catalog_source import (
    ExternalCatalogSource,
)
from backend.domain.products.entities.external_product_record import (
    ExternalProductRecord,
)
from backend.domain.products.exceptions import (
    ExternalCatalogUnavailableError,
    UnknownCatalogProviderError,
)
from backend.domain.products.external_enums import ExternalProviderType


class ExternalCatalogAdapter(Protocol):
    provider_type: ExternalProviderType

    def search(self, query: str) -> list[dict]: ...


class ExternalProductCatalogGateway:
    def __init__(self, registry) -> None:
        self._registry = registry

    def search(self, source: ExternalCatalogSource, query: str) -> list[ExternalProductRecord]:
        if not source.active:
            raise ExternalCatalogUnavailableError(
                f"La fuente {source.code} está inactiva")
        adapter = self._registry.get(source.provider_type)
        if adapter is None:
            raise UnknownCatalogProviderError(
                f"Sin adaptador para el proveedor {source.provider_type.value}")
        raw_records = adapter.search(query)
        return [self._to_record(source, raw) for raw in raw_records]

    @staticmethod
    def _to_record(source: ExternalCatalogSource, raw: dict) -> ExternalProductRecord:
        return ExternalProductRecord(
            source_id=source.id,
            external_id=str(raw.get("external_id") or ""),
            name=str(raw.get("name") or ""),
            barcode=raw.get("barcode"),
            brand=raw.get("brand"),
            category=raw.get("category"),
            net_weight=raw.get("net_weight"),
            unit=raw.get("unit"),
            raw_payload=raw.get("raw_payload"))
