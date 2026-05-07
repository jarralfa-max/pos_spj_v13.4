"""Nominatim (OpenStreetMap) address provider — used as offline fallback.

Wraps the existing urllib-based geocoding logic. Only activated when Mapbox
is unreachable or unconfigured.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from core.integrations.address_provider import AddressProvider

logger = logging.getLogger("spj.integrations.nominatim")

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT    = "SPJ-POS-ERP/13.4 (delivery-module; fallback)"


class NominatimProvider(AddressProvider):
    """OpenStreetMap Nominatim geocoder (fallback / offline mode)."""

    def __init__(self, timeout: int = 4, country_codes: str = "mx") -> None:
        self._timeout = timeout
        self._country_codes = country_codes

    def autocomplete(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if len(q) < 4:
            return []
        params = urllib.parse.urlencode({
            "q": q,
            "format": "json",
            "addressdetails": 1,
            "limit": limit,
            "countrycodes": self._country_codes,
        })
        url = f"{_NOMINATIM_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            results = []
            for p in payload:
                results.append({
                    "label":    p.get("display_name", ""),
                    "lat":      float(p["lat"]) if p.get("lat") else None,
                    "lng":      float(p["lon"]) if p.get("lon") else None,
                    "place_id": str(p.get("place_id", "")),
                })
            logger.debug("Nominatim autocomplete query=%r results=%d", q[:40], len(results))
            return results
        except Exception as exc:
            logger.debug("Nominatim autocomplete error: %s", exc)
            return []

    def geocode(self, address: str) -> Optional[Dict[str, float]]:
        results = self.autocomplete(address, limit=1)
        if not results:
            return None
        first = results[0]
        lat, lng = first.get("lat"), first.get("lng")
        if lat is None or lng is None:
            return None
        return {"lat": lat, "lng": lng, "label": first.get("label", "")}
