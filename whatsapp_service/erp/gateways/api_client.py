from __future__ import annotations
from typing import Any


class ERPApiClient:
    """HTTP client wrapper used by ERPBridge facade."""

    def __init__(self, bridge):
        self._bridge = bridge

    def get(self, path: str, **params) -> Any:
        return self._bridge._api_get(path, **params)

    def post(self, path: str, body: dict) -> Any:
        return self._bridge._api_post(path, body)

    def patch(self, path: str, **params) -> Any:
        return self._bridge._api_patch(path, **params)
