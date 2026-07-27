"""GeocodingService — orchestrates provider selection and shared cache.

Public interface is unchanged: autocomplete(query) and geocode(address).
DeliveryService and all existing callers work without modification.

Provider selection order:
  1. MapboxAddressProvider  (primary — fast, regional bias, connection-pooled)
  2. NominatimProvider      (fallback — free, offline-safe)

Both share one module-level AddressCache so warm queries are answered from
memory regardless of which provider originally populated the entry.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from core.cache.address_cache import AddressCache
from core.integrations.address_provider import AddressProvider

logger = logging.getLogger("spj.services.geocoding")

# ── Shared module-level cache ─────────────────────────────────────────────────
_cache = AddressCache(
    max_size=int(os.environ.get("GEOCODING_CACHE_SIZE", "200")),
    ttl=int(os.environ.get("GEOCODING_CACHE_TTL", "3600")),
)

_MIN_CHARS = int(os.environ.get("DELIVERY_MIN_SEARCH_CHARS", "5"))


def _build_primary() -> Optional[AddressProvider]:
    try:
        from core.integrations.mapbox_provider import MapboxAddressProvider
        return MapboxAddressProvider()
    except Exception as exc:
        logger.warning("MapboxAddressProvider unavailable: %s", exc)
        return None


def _build_fallback() -> AddressProvider:
    from core.integrations.nominatim_provider import NominatimProvider
    return NominatimProvider()


class GeocodingService:
    """Facade that routes geocoding through provider(s) with LRU+TTL cache.

    Parameters
    ----------
    primary:
        Primary AddressProvider. Defaults to MapboxAddressProvider.
    fallback:
        Fallback provider used when primary returns empty or errors.
        Defaults to NominatimProvider.
    timeout:
        Legacy kwarg kept for backwards compatibility; each provider
        manages its own timeout internally.
    """

    def __init__(
        self,
        primary: Optional[AddressProvider] = None,
        fallback: Optional[AddressProvider] = None,
        timeout: int = 4,   # backwards-compat only
    ) -> None:
        self._primary  = primary  if primary  is not None else _build_primary()
        self._fallback = fallback if fallback is not None else _build_fallback()
        self._cache    = _cache

    # ── Public interface (identical signature to legacy) ──────────────────────

    def autocomplete(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return up to *limit* address suggestions.

        Cache-first. On miss tries primary, then fallback.
        Never raises; always returns a list (may be empty).
        """
        q = (query or "").strip()
        if len(q) < _MIN_CHARS:
            return []

        cache_key = f"ac:{q.lower()}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        results = self._try_primary_autocomplete(q, limit)
        if not results:
            results = self._try_fallback_autocomplete(q, limit)

        if results:
            self._cache.put(cache_key, results)

        logger.debug(
            "autocomplete q=%r provider=%s results=%d cache=%s",
            q[:40],
            "primary" if results and self._primary else "fallback",
            len(results),
            self._cache.stats,
        )
        return results

    def geocode(self, address: str) -> Optional[Dict[str, float]]:
        """Resolve full address to {lat, lng, label}. Returns None on failure."""
        q = (address or "").strip()
        if not q:
            return None

        cache_key = f"geo:{q.lower()}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        result = self._try_primary_geocode(q)
        if result is None:
            result = self._try_fallback_geocode(q)

        if result:
            self._cache.put(cache_key, result)
        return result

    def cache_stats(self) -> dict:
        return self._cache.stats

    # ── Internal ──────────────────────────────────────────────────────────────

    def _try_primary_autocomplete(self, q: str, limit: int) -> List[Dict[str, Any]]:
        if self._primary is None:
            return []
        try:
            return self._primary.autocomplete(q, limit) or []
        except Exception as exc:
            logger.warning("primary.autocomplete failed: %s", exc)
            return []

    def _try_fallback_autocomplete(self, q: str, limit: int) -> List[Dict[str, Any]]:
        try:
            return self._fallback.autocomplete(q, limit) or []
        except Exception as exc:
            logger.debug("fallback.autocomplete failed: %s", exc)
            return []

    def _try_primary_geocode(self, q: str) -> Optional[Dict[str, float]]:
        if self._primary is None:
            return None
        try:
            return self._primary.geocode(q)
        except Exception as exc:
            logger.warning("primary.geocode failed: %s", exc)
            return None

    def _try_fallback_geocode(self, q: str) -> Optional[Dict[str, float]]:
        try:
            return self._fallback.geocode(q)
        except Exception as exc:
            logger.debug("fallback.geocode failed: %s", exc)
            return None
