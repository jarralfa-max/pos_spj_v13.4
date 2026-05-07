"""Mapbox Geocoding API v6 provider.

Uses a shared requests.Session with connection pooling so that repeated
autocomplete calls reuse the same TCP connection. All I/O is synchronous from
the caller's perspective — callers MUST invoke from a background thread
(QRunnable/QThreadPool), never from the Qt main/GUI thread.

Configuration (environment variables):
    MAPBOX_TOKEN               — required; Mapbox public access token
    MAPBOX_COUNTRY             — default "mx"; ISO country code(s), comma-sep
    MAPBOX_AUTOCOMPLETE_LIMIT  — default 5; max suggestions returned
    MAPBOX_TIMEOUT             — default 5; HTTP timeout in seconds

These variables are read once at import time, so they can also be set
programmatically before the first import (e.g. in app bootstrap).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

from core.integrations.address_provider import AddressProvider

logger = logging.getLogger("spj.integrations.mapbox")

# ── Configuration (env-driven, never hardcoded in source) ────────────────────

_COUNTRY = os.environ.get("MAPBOX_COUNTRY", "mx")
_LIMIT   = int(os.environ.get("MAPBOX_AUTOCOMPLETE_LIMIT", "5"))
_TIMEOUT = int(os.environ.get("MAPBOX_TIMEOUT", "5"))


def _resolve_token() -> str:
    """Return MAPBOX_TOKEN from env or from .env.delivery file (lazy load).

    Searches for .env.delivery relative to this file and relative to cwd.
    Caches the result back into os.environ so subsequent calls are O(1).
    """
    token = os.environ.get("MAPBOX_TOKEN", "")
    if token:
        return token

    candidates = [
        os.path.join(os.path.dirname(__file__), "../../../.env.delivery"),
        os.path.join(os.path.dirname(__file__), "../../.env.delivery"),
        os.path.join(os.getcwd(), ".env.delivery"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    if key.strip() == "MAPBOX_TOKEN":
                        val = val.strip().strip('"').strip("'")
                        if val:
                            os.environ["MAPBOX_TOKEN"] = val
                            logger.debug("MAPBOX_TOKEN loaded from %s", path)
                            return val
        except (FileNotFoundError, PermissionError):
            continue
    return ""

_BASE_URL    = "https://api.mapbox.com/search/geocode/v6"
_USER_AGENT  = "SPJ-POS-ERP/13.4 (delivery-module)"


# ── Thread-safe session singleton ────────────────────────────────────────────

class _SessionPool:
    """Lazily-initialised, thread-safe requests.Session singleton."""

    _session: Optional[requests.Session] = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> requests.Session:
        if cls._session is None:
            with cls._lock:
                if cls._session is None:
                    s = requests.Session()
                    s.headers.update({
                        "User-Agent": _USER_AGENT,
                        "Accept": "application/json",
                    })
                    adapter = HTTPAdapter(
                        pool_connections=2,
                        pool_maxsize=8,
                        max_retries=0,
                    )
                    s.mount("https://", adapter)
                    cls._session = s
                    logger.debug("Mapbox HTTP session initialised (pool_maxsize=8)")
        return cls._session

    @classmethod
    def close(cls) -> None:
        with cls._lock:
            if cls._session is not None:
                cls._session.close()
                cls._session = None


# ── Provider ─────────────────────────────────────────────────────────────────

class MapboxAddressProvider(AddressProvider):
    """Mapbox Geocoding v6 forward-search implementation.

    Thread-safe. Instances may be shared across QRunnable workers.
    """

    def __init__(
        self,
        token: str = "",
        country: str = _COUNTRY,
        limit: int = _LIMIT,
        timeout: int = _TIMEOUT,
        proximity_lng: Optional[float] = None,
        proximity_lat: Optional[float] = None,
    ) -> None:
        resolved = token or _resolve_token()
        if not resolved:
            raise ValueError(
                "MAPBOX_TOKEN is required. Set the env var or add it to .env.delivery"
            )
        self._token   = resolved
        self._country = country
        self._limit   = min(max(limit, 1), 10)
        self._timeout = timeout
        self._proximity_lng = proximity_lng
        self._proximity_lat = proximity_lat

    # ── Public interface ──────────────────────────────────────────────────────

    def autocomplete(self, query: str, limit: int = 0) -> List[Dict[str, Any]]:
        """Return up to *limit* (or instance default) address suggestions.

        Safe to call from any thread. Returns [] on any error — never raises.
        """
        q = (query or "").strip()
        if not q:
            return []
        effective_limit = limit if limit > 0 else self._limit
        t0 = time.monotonic()
        try:
            results = self._forward(q, effective_limit)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.debug(
                "Mapbox autocomplete query=%r results=%d elapsed=%.0fms",
                q[:40], len(results), elapsed_ms,
            )
            return results
        except Exception as exc:
            logger.warning("Mapbox autocomplete error query=%r: %s", q[:40], exc)
            return []

    def geocode(self, address: str) -> Optional[Dict[str, float]]:
        """Resolve address to {lat, lng, label}. Returns None on failure."""
        results = self.autocomplete(address, limit=1)
        if not results:
            return None
        first = results[0]
        lat = first.get("lat")
        lng = first.get("lng")
        if lat is None or lng is None:
            return None
        return {"lat": float(lat), "lng": float(lng), "label": first.get("label", "")}

    def health_check(self) -> bool:
        """Ping Mapbox with a trivial query; True if reachable."""
        try:
            session = _SessionPool.get()
            resp = session.get(
                f"{_BASE_URL}/forward",
                params={"q": "test", "access_token": self._token, "limit": "1"},
                timeout=3,
            )
            ok = resp.status_code < 500
            logger.debug("Mapbox health_check status=%d ok=%s", resp.status_code, ok)
            return ok
        except Exception as exc:
            logger.warning("Mapbox health_check failed: %s", exc)
            return False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _forward(self, query: str, limit: int) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "q": query,
            "access_token": self._token,
            "country": self._country,
            "limit": limit,
        }
        if self._proximity_lng is not None and self._proximity_lat is not None:
            params["proximity"] = f"{self._proximity_lng},{self._proximity_lat}"

        session = _SessionPool.get()
        resp = session.get(
            f"{_BASE_URL}/forward",
            params=params,
            timeout=self._timeout,
        )
        if resp.status_code == 429:
            logger.warning("Mapbox rate-limit hit (429)")
            return []
        resp.raise_for_status()
        return self._parse(resp.json())

    def _parse(self, payload: dict) -> List[Dict[str, Any]]:
        features = payload.get("features") or []
        results: List[Dict[str, Any]] = []
        for f in features:
            props = f.get("properties") or {}
            geom  = f.get("geometry") or {}
            coords = props.get("coordinates") or {}

            lat = coords.get("latitude")
            lng = coords.get("longitude")
            if lat is None and geom.get("type") == "Point":
                lng, lat = geom.get("coordinates", [None, None])

            label = (
                props.get("full_address")
                or props.get("place_formatted")
                or props.get("name")
                or ""
            )
            results.append({
                "label":      label,
                "lat":        float(lat) if lat is not None else None,
                "lng":        float(lng) if lng is not None else None,
                "place_id":   props.get("mapbox_id") or f.get("id"),
                "place_name": props.get("name") or label,
                "relevance":  props.get("match_code", {}).get("confidence") if isinstance(props.get("match_code"), dict) else None,
            })
        return results
