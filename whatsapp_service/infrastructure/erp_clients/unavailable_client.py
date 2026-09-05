# infrastructure/erp_clients/unavailable_client.py — WA-9
"""Cuando `ERPBridge`/`ProductMatcher` reales no pudieron construirse en
este proceso (p. ej. base sin el esquema legacy del ERP — el caso de casi
todos los tests de este árbol, que solo montan el esquema WA-3), los
clientes ERP se registran como esta clase en vez de omitirse en silencio.
Cualquier método invocado falla explícito — nunca finge un resultado."""
from __future__ import annotations

from typing import Any


class ErpClientUnavailableError(RuntimeError):
    pass


class UnavailableErpClient:
    def __init__(self, client_name: str, reason: str = "") -> None:
        self._client_name = client_name
        self._reason = reason

    def __getattr__(self, name: str) -> Any:
        async def _raise(*args: Any, **kwargs: Any) -> Any:
            detail = f" ({self._reason})" if self._reason else ""
            raise ErpClientUnavailableError(
                f"{self._client_name}.{name}: cliente ERP no disponible en este proceso{detail}"
            )

        return _raise
