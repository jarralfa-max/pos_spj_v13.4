"""Open Food Facts HTTP client (§15).

Real network client that implements the ``RawCatalogClient`` port
(``fetch(query) -> list[dict]``) consumed by :class:`OpenFoodFactsAdapter`.

The adapter maps/normalises the raw OFF product dicts; this client only performs
the HTTP call and returns the provider's raw ``products`` list. Two lookup modes:

* a numeric query (an EAN/UPC barcode) resolves the single product via the
  product endpoint;
* any other query runs a keyword search.

Network I/O is synchronous — call from a background thread, never the Qt GUI
thread. The HTTP transport is injectable (``transport(url, params) -> (status,
payload)``) so tests run without touching the network; the default transport
uses a pooled ``requests.Session`` that honours the environment proxy
(``HTTPS_PROXY``) and CA bundle (``REQUESTS_CA_BUNDLE``) automatically, like the
other integrations in this codebase.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

logger = logging.getLogger("spj.integrations.open_food_facts")

# canonical OFF fields we request (keeps payloads small and stable)
_FIELDS = "code,product_name,brands,categories,quantity,product_quantity_unit"

# env-driven config with sane fallbacks (infra tuning, not UI defaults)
_BASE_URL = os.environ.get("OFF_BASE_URL", "https://world.openfoodfacts.org").rstrip("/")
_PAGE_SIZE = int(os.environ.get("OFF_PAGE_SIZE", "20"))
_TIMEOUT = int(os.environ.get("OFF_TIMEOUT", "8"))
# OFF asks every client to send a descriptive, contactable User-Agent.
_USER_AGENT = os.environ.get(
    "OFF_USER_AGENT", "SPJ-POS-ERP/13.4 (product-catalog; +https://spj.example)")

# transport(url, params) -> (status_code, payload_dict)
Transport = Callable[[str, Optional[dict]], "tuple[int, dict]"]


class _SessionPool:
    """Lazily-initialised, thread-safe ``requests.Session`` singleton."""

    _session = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        if cls._session is None:
            with cls._lock:
                if cls._session is None:
                    import requests
                    from requests.adapters import HTTPAdapter

                    s = requests.Session()
                    s.headers.update({
                        "User-Agent": _USER_AGENT,
                        "Accept": "application/json",
                    })
                    s.mount("https://", HTTPAdapter(pool_connections=2,
                                                    pool_maxsize=8, max_retries=0))
                    cls._session = s
                    logger.debug("Open Food Facts HTTP session initialised")
        return cls._session

    @classmethod
    def close(cls) -> None:
        with cls._lock:
            if cls._session is not None:
                cls._session.close()
                cls._session = None


def _default_transport(url: str, params: Optional[dict]) -> "tuple[int, dict]":
    """Perform the GET with the pooled session; return (status, json-or-{})."""
    resp = _SessionPool.get().get(url, params=params, timeout=_TIMEOUT)
    try:
        payload = resp.json() if resp.content else {}
    except ValueError:
        payload = {}
    return resp.status_code, (payload if isinstance(payload, dict) else {})


class OpenFoodFactsHttpClient:
    """Fetches raw product dicts from the Open Food Facts REST API."""

    def __init__(self, base_url: str = _BASE_URL, page_size: int = _PAGE_SIZE,
                 transport: Optional[Transport] = None) -> None:
        self._base_url = (base_url or _BASE_URL).rstrip("/")
        self._page_size = max(1, min(int(page_size or _PAGE_SIZE), 100))
        self._transport: Transport = transport or _default_transport

    # ── public port ────────────────────────────────────────────────────────
    def fetch(self, query: str) -> list[dict]:
        """Return the raw OFF product dicts for *query* (barcode or keywords).

        Raises on any transport/HTTP failure so the adapter can surface it as an
        ``ExternalCatalogUnavailableError`` domain error.
        """
        q = (query or "").strip()
        if not q:
            return []
        if self._is_barcode(q):
            return self._fetch_by_barcode(q)
        return self._search(q)

    # ── internals ──────────────────────────────────────────────────────────
    @staticmethod
    def _is_barcode(query: str) -> bool:
        return query.isdigit() and 8 <= len(query) <= 14

    def _fetch_by_barcode(self, barcode: str) -> list[dict]:
        url = f"{self._base_url}/api/v2/product/{barcode}.json"
        status, payload = self._transport(url, {"fields": _FIELDS})
        if status == 404:
            return []  # unknown barcode is a normal empty result, not a failure
        self._raise_for_status(status, url)
        # OFF returns status: 1 (found) / 0 (not found)
        if payload.get("status") in (0, "0", "failure") or not payload.get("product"):
            return []
        return [payload["product"]]

    def _search(self, query: str) -> list[dict]:
        url = f"{self._base_url}/cgi/search.pl"
        params = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": self._page_size,
            "fields": _FIELDS,
        }
        status, payload = self._transport(url, params)
        self._raise_for_status(status, url)
        products = payload.get("products")
        return list(products) if isinstance(products, list) else []

    @staticmethod
    def _raise_for_status(status: int, url: str) -> None:
        if status < 200 or status >= 300:
            raise ConnectionError(
                f"Open Food Facts respondió HTTP {status} en {url}")
