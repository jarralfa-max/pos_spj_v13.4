"""Address provider abstraction — UI and services depend on this interface only.

Neither MapboxAddressProvider nor NominatimProvider are imported directly by
any module outside core/integrations. Consumers accept AddressProvider.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class AddressProvider:
    """Geocoding provider interface.

    Implementations must be thread-safe: autocomplete() and geocode() are
    called from QRunnable workers (off the Qt main thread).
    """

    def autocomplete(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return up to *limit* address suggestions for the given query.

        Each result dict must contain at minimum:
            label (str): human-readable display string
            lat   (float | None)
            lng   (float | None)

        Optional keys: place_id, place_name, relevance.
        """
        raise NotImplementedError

    def geocode(self, address: str) -> Optional[Dict[str, float]]:
        """Resolve a full address string to {"lat": float, "lng": float, "label": str}.

        Returns None on failure; never raises.
        """
        raise NotImplementedError

    def health_check(self) -> bool:
        """Return True if the provider is reachable."""
        return True
