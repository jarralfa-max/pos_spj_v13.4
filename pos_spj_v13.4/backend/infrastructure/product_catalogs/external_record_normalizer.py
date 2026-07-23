"""External record normalizer (§15).

Turns a provider-specific raw payload into the canonical dict the gateway expects
(external_id, name, barcode, brand, category, net_weight, unit, raw_payload) using
a per-provider field map. Keeps the adapters thin and the mapping declarative.
"""

from __future__ import annotations

import json

_CANONICAL_FIELDS = ("external_id", "name", "barcode", "brand", "category",
                     "net_weight", "unit")


def normalize(raw: dict, field_map: dict[str, str]) -> dict:
    """``field_map`` maps a canonical field → the provider's key."""
    out: dict = {}
    for canonical in _CANONICAL_FIELDS:
        source_key = field_map.get(canonical)
        value = raw.get(source_key) if source_key else None
        out[canonical] = None if value is None else str(value).strip()
    out["raw_payload"] = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    return out
