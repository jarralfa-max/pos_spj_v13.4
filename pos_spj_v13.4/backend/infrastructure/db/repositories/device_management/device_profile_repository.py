"""SqliteDeviceProfileRepository — persists `DeviceProfile` (SET-7).
Implements
`backend.domain.device_management.repository_ports.DeviceProfileRepositoryPort`.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import ConnectionType, DeviceCapabilityCode, DeviceType
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.device_capability import DeviceCapability
from backend.domain.device_management.value_objects.network_endpoint import NetworkEndpoint
from backend.domain.device_management.value_objects.serial_port_profile import SerialPortProfile
from backend.infrastructure.db.repositories.device_management.base import DeviceManagementRepositoryBase

_COLS = (
    "id, name, device_type, manufacturer, model, connection_type, serial_port_json,"
    " network_endpoint_json, extra_parameters_json, credential_reference, capabilities_json,"
    " paper_profile, protocol, driver_name, timeout_seconds, retry_max_attempts,"
    " health_check_enabled, active, created_at, updated_at"
)


def _serialize_serial_port(serial_port: SerialPortProfile | None) -> str | None:
    if serial_port is None:
        return None
    return json.dumps({
        "port": serial_port.port, "baud_rate": serial_port.baud_rate, "parity": serial_port.parity,
        "data_bits": serial_port.data_bits, "stop_bits": serial_port.stop_bits,
        "read_timeout_seconds": str(serial_port.read_timeout_seconds),
    })


def _deserialize_serial_port(raw: str | None) -> SerialPortProfile | None:
    if raw is None:
        return None
    data = json.loads(raw)
    return SerialPortProfile(
        port=data["port"], baud_rate=data["baud_rate"], parity=data["parity"],
        data_bits=data["data_bits"], stop_bits=data["stop_bits"],
        read_timeout_seconds=Decimal(data["read_timeout_seconds"]),
    )


def _serialize_network_endpoint(endpoint: NetworkEndpoint | None) -> str | None:
    if endpoint is None:
        return None
    return json.dumps({"host": endpoint.host, "port": endpoint.port, "use_tls": endpoint.use_tls})


def _deserialize_network_endpoint(raw: str | None) -> NetworkEndpoint | None:
    if raw is None:
        return None
    data = json.loads(raw)
    return NetworkEndpoint(host=data["host"], port=data["port"], use_tls=data["use_tls"])


def _serialize_capabilities(capabilities: tuple[DeviceCapability, ...]) -> str:
    return json.dumps([{"code": c.code.value, "parameters": c.parameters} for c in capabilities])


def _deserialize_capabilities(raw: str) -> tuple[DeviceCapability, ...]:
    return tuple(
        DeviceCapability(DeviceCapabilityCode(item["code"]), item["parameters"])
        for item in json.loads(raw)
    )


class SqliteDeviceProfileRepository(DeviceManagementRepositoryBase):
    def save(self, profile: DeviceProfile) -> None:
        self._execute(
            f"INSERT INTO device_profiles ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " name=excluded.name, device_type=excluded.device_type,"
            " manufacturer=excluded.manufacturer, model=excluded.model,"
            " connection_type=excluded.connection_type, serial_port_json=excluded.serial_port_json,"
            " network_endpoint_json=excluded.network_endpoint_json,"
            " extra_parameters_json=excluded.extra_parameters_json,"
            " credential_reference=excluded.credential_reference,"
            " capabilities_json=excluded.capabilities_json, paper_profile=excluded.paper_profile,"
            " protocol=excluded.protocol, driver_name=excluded.driver_name,"
            " timeout_seconds=excluded.timeout_seconds, retry_max_attempts=excluded.retry_max_attempts,"
            " health_check_enabled=excluded.health_check_enabled, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(profile),
        )

    def get(self, profile_id: str) -> DeviceProfile | None:
        row = self._query_one(f"SELECT {_COLS} FROM device_profiles WHERE id=?", (profile_id,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[DeviceProfile]:
        rows = self._query(f"SELECT {_COLS} FROM device_profiles WHERE active=1 ORDER BY name")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(profile: DeviceProfile) -> tuple:
        connection = profile.connection_profile
        return (
            profile.id, profile.name, profile.device_type.value, profile.manufacturer, profile.model,
            connection.connection_type.value, _serialize_serial_port(connection.serial_port),
            _serialize_network_endpoint(connection.network_endpoint),
            json.dumps(connection.extra_parameters), connection.credential_reference,
            _serialize_capabilities(profile.capabilities), profile.paper_profile, profile.protocol,
            profile.driver_name, profile.timeout_seconds, profile.retry_max_attempts,
            int(profile.health_check_enabled), int(profile.active), profile.created_at, profile.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> DeviceProfile:
        connection_profile = ConnectionProfile(
            connection_type=ConnectionType(row["connection_type"]),
            serial_port=_deserialize_serial_port(row["serial_port_json"]),
            network_endpoint=_deserialize_network_endpoint(row["network_endpoint_json"]),
            extra_parameters=json.loads(row["extra_parameters_json"] or "{}"),
            credential_reference=row["credential_reference"],
        )
        return DeviceProfile(
            id=row["id"], name=row["name"], device_type=DeviceType(row["device_type"]),
            connection_profile=connection_profile, manufacturer=row["manufacturer"] or "",
            model=row["model"] or "", capabilities=_deserialize_capabilities(row["capabilities_json"]),
            paper_profile=row["paper_profile"], protocol=row["protocol"] or "",
            driver_name=row["driver_name"] or "", timeout_seconds=row["timeout_seconds"],
            retry_max_attempts=row["retry_max_attempts"],
            health_check_enabled=bool(row["health_check_enabled"]), active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
