"""NetworkEndpoint — connection details for NETWORK/HTTP/WEBSOCKET
devices (network-attached printers, terminal APIs, ...). See §18-19.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.device_management.exceptions import DeviceInvalidValueError


@dataclass(frozen=True, slots=True)
class NetworkEndpoint:
    host: str
    port: int
    use_tls: bool = False

    @classmethod
    def create(cls, *, host: str, port: int, use_tls: bool = False) -> "NetworkEndpoint":
        if not host.strip():
            raise DeviceInvalidValueError("host es obligatorio")
        if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
            raise DeviceInvalidValueError(f"port debe ser un entero entre 1 y 65535, recibido {port!r}")
        return cls(host.strip(), port, bool(use_tls))
