"""CSV catalog adapter (§15) — imports products from a CSV feed.

Parses in-memory CSV text (no network) and normalizes each row to the canonical
dict. A filter on the query narrows rows by a case-insensitive name substring.
"""

from __future__ import annotations

import csv
import io

from backend.domain.products.external_enums import ExternalProviderType
from backend.infrastructure.product_catalogs.external_record_normalizer import normalize

_CSV_FIELD_MAP = {
    "external_id": "sku", "name": "name", "barcode": "barcode", "brand": "brand",
    "category": "category", "net_weight": "net_weight", "unit": "unit",
}


class CsvCatalogAdapter:
    provider_type = ExternalProviderType.CSV

    def __init__(self, csv_text: str, field_map: dict[str, str] | None = None) -> None:
        self._csv_text = csv_text or ""
        self._field_map = field_map or _CSV_FIELD_MAP

    def search(self, query: str) -> list[dict]:
        needle = (query or "").strip().lower()
        rows = list(csv.DictReader(io.StringIO(self._csv_text)))
        out: list[dict] = []
        for row in rows:
            normalized = normalize(row, self._field_map)
            if needle and needle not in (normalized.get("name") or "").lower():
                continue
            out.append(normalized)
        return out
