"""ProductMatchingService — link an external record to an existing product (§15).

Matches by active barcode first (exact), then by normalized name. The caller
provides lookup callables (barcode → product_id, normalized_name → product_id) so
the service stays free of persistence. Returns the matched product id or None.
"""

from __future__ import annotations

from typing import Callable

from backend.domain.products.entities.external_product_record import (
    ExternalProductRecord,
)
from backend.domain.products.value_objects.product_name import normalize_name

BarcodeLookup = Callable[[str], str | None]
NameLookup = Callable[[str], str | None]


class ProductMatchingService:
    def match(
        self,
        record: ExternalProductRecord,
        *,
        by_barcode: BarcodeLookup,
        by_normalized_name: NameLookup,
    ) -> str | None:
        if record.barcode:
            hit = by_barcode(record.barcode)
            if hit:
                return hit
        normalized = normalize_name(record.name)
        if normalized:
            return by_normalized_name(normalized)
        return None
