from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

logger = logging.getLogger("spj.services.geocoding")


class GeocodingService:
    def __init__(self, timeout: int = 4):
        self.timeout = timeout
        self._headers = {"User-Agent": "SPJ-POS-Delivery/1.0"}

    def autocomplete(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        if not query or len(query.strip()) < 4:
            return []
        params = urllib.parse.urlencode({"q": query, "format": "json", "addressdetails": 1, "limit": limit})
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        req = urllib.request.Request(url, headers=self._headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return [
                {
                    "label": p.get("display_name", ""),
                    "lat": p.get("lat"),
                    "lng": p.get("lon"),
                }
                for p in payload
            ]
        except Exception as exc:
            logger.debug("autocomplete error: %s", exc)
            return []

    def geocode(self, address: str) -> Optional[Dict[str, float]]:
        suggestions = self.autocomplete(address, limit=1)
        if not suggestions:
            return None
        first = suggestions[0]
        try:
            return {"lat": float(first["lat"]), "lng": float(first["lng"]), "label": first["label"]}
        except Exception:
            return None
