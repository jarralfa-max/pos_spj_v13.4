"""ConnectionProfile — how a `DeviceProfile` is reached (§18-19).

Holds exactly the typed detail its `connection_type` needs
(`SerialPortProfile` for SERIAL, `NetworkEndpoint` for NETWORK/HTTP/
WEBSOCKET) plus free-form `extra_parameters` for USB/BLUETOOTH/SYSTEM/
VIRTUAL, which don't need a port/host.

§19: "Los secretos o credenciales no deben guardarse dentro de
connection_parameters. Usar referencia segura." — enforced here, not
just documented: `extra_parameters` is scanned for secret-looking keys
and rejected outright; the one legitimate way to reference a credential
is `credential_reference` (a `SECRET_REFERENCE`-style name into
`SecretStoreGateway`, never the raw secret).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.device_management.enums import NETWORK_ADDRESSED_CONNECTION_TYPES, ConnectionType
from backend.domain.device_management.exceptions import DeviceInvalidValueError
from backend.domain.device_management.value_objects.network_endpoint import NetworkEndpoint
from backend.domain.device_management.value_objects.serial_port_profile import SerialPortProfile

_SECRET_LIKE_SUBSTRINGS = (
    "password", "secret", "token", "credential", "apikey", "api_key",
    "privatekey", "private_key", "auth",
)


def _assert_no_secret_like_keys(parameters: dict[str, str]) -> None:
    offenders = [
        key for key in parameters
        if any(marker in key.strip().lower().replace(" ", "") for marker in _SECRET_LIKE_SUBSTRINGS)
    ]
    if offenders:
        raise DeviceInvalidValueError(
            f"connection_parameters no puede contener claves con apariencia de secreto: {offenders}. "
            "Usa credential_reference (SecretStoreGateway) en su lugar (§19)."
        )


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
    connection_type: ConnectionType
    serial_port: SerialPortProfile | None = None
    network_endpoint: NetworkEndpoint | None = None
    extra_parameters: dict[str, str] = field(default_factory=dict)
    credential_reference: str | None = None

    @classmethod
    def create(
        cls, connection_type: ConnectionType, *, serial_port: SerialPortProfile | None = None,
        network_endpoint: NetworkEndpoint | None = None, extra_parameters: dict[str, str] | None = None,
        credential_reference: str | None = None,
    ) -> "ConnectionProfile":
        if connection_type is ConnectionType.SERIAL and serial_port is None:
            raise DeviceInvalidValueError("connection_type=SERIAL requiere serial_port")
        if connection_type in NETWORK_ADDRESSED_CONNECTION_TYPES and network_endpoint is None:
            raise DeviceInvalidValueError(f"connection_type={connection_type.value} requiere network_endpoint")

        params = dict(extra_parameters or {})
        _assert_no_secret_like_keys(params)

        return cls(
            connection_type=connection_type, serial_port=serial_port, network_endpoint=network_endpoint,
            extra_parameters=params,
            credential_reference=credential_reference.strip() if credential_reference else None,
        )
