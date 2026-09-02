"""Use cases for the "Dispositivos" section of the Configuración
workspace — the first real CRUD wired for this section (SET-25
follow-up). Thin orchestration over `backend/domain/device_management/`
(SET-7): construct the value objects, apply the domain rule, persist —
no business logic lives here (that's `Device`/`DeviceProfile`'s own
methods and `ConnectionProfile.create`'s validation).

`ChangeDeviceStatusUseCase` is deliberately ONE use case for all 5
transitions (activate/deactivate/block/unblock/retire) rather than 5
near-identical classes — each domain method still fully owns its own
transition rule; this only picks which one to call.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import (
    CASH_DRAWER_DEVICE_TYPES,
    PAYMENT_TERMINAL_DEVICE_TYPES,
    PRINTER_DEVICE_TYPES,
    READER_DEVICE_TYPES,
    SCALE_DEVICE_TYPES,
    ConnectionType,
    DeviceCapabilityCode,
    DeviceType,
)
from backend.domain.device_management.exceptions import DeviceNotFoundError, DeviceProfileNotFoundError
from backend.domain.device_management.policies.cash_drawer_profile_policy import (
    assert_valid_cash_drawer_profile,
)
from backend.domain.device_management.policies.payment_terminal_profile_policy import (
    assert_valid_payment_terminal_profile,
)
from backend.domain.device_management.policies.printer_profile_policy import assert_valid_printer_profile
from backend.domain.device_management.policies.reader_profile_policy import (
    REQUIRED_CAPABILITY_BY_TYPE,
    assert_valid_reader_profile,
)
from backend.domain.device_management.policies.scale_profile_policy import assert_valid_scale_profile
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.device_capability import DeviceCapability
from backend.domain.device_management.value_objects.device_identifier import DeviceIdentifier
from backend.domain.device_management.value_objects.network_endpoint import NetworkEndpoint
from backend.domain.device_management.value_objects.serial_port_profile import SerialPortProfile
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository


class DeviceStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"
    BLOCK = "BLOCK"
    UNBLOCK = "UNBLOCK"
    RETIRE = "RETIRE"


class RegisterDeviceProfileUseCase:
    """Builds the right `ConnectionProfile` shape for the chosen
    `connection_type` — SERIAL needs `serial_port`/`baud_rate`, NETWORK
    needs `host`/`port`; everything else (USB/BLUETOOTH/SYSTEM/VIRTUAL)
    needs neither. HTTP/WEBSOCKET are deliberately not offered by the UI
    yet (see `docs/refactor/SET-25_legacy_removal_report.md`).

    SET-8 follow-up: when `device_type` is one of the 4 printer types
    (`PRINTER_DEVICE_TYPES`), `paper_profile`/`protocol` are validated via
    `printer_profile_policy.assert_valid_printer_profile()` — §23's "no
    asumir que toda impresora es ESC/POS" enforced at registration time,
    not left to a UI-only combo box the use case never checks.

    SET-9 follow-up: scale/reader profiles need a required
    `DeviceCapability` to pass their own policy
    (`assert_valid_scale_profile`/`assert_valid_reader_profile` — §22) —
    `capabilities` was always an empty tuple before this, so no scale or
    reader profile could ever be registered. The required capability
    (WEIGH for scales, SCAN_1D/SCAN_2D for readers) is deterministic from
    `device_type`, so it's derived here rather than asked of the UI —
    same reasoning printer capabilities (CUT/DRAWER_PULSE/...) stay
    unexposed: they're optional extras, not gating requirements.

    SET-10 follow-up: cash drawers need `DRAWER_PULSE` — deterministic
    from `device_type`, derived the same way as scales/readers. Payment
    terminals need *at least one* of 5 real payment capabilities
    (swipe/chip/contactless/accept-cash/dispense-cash) — genuine choice,
    not deterministic, so `payment_capabilities` is the one capability
    input this use case actually accepts from the caller."""

    def __init__(self, connection) -> None:
        self._conn = connection
        self._profiles = SqliteDeviceProfileRepository(connection)

    def execute(
        self, *, name: str, device_type: DeviceType | str, connection_type: ConnectionType | str,
        manufacturer: str = "", model: str = "", serial_port: str = "", baud_rate: int | None = None,
        host: str = "", port: int | None = None, paper_profile: str = "", protocol: str = "",
        driver_name: str = "", payment_capabilities: tuple[str, ...] = (),
    ) -> DeviceProfile:
        device_type = DeviceType(device_type)
        connection_type = ConnectionType(connection_type)

        serial_port_vo = None
        if connection_type is ConnectionType.SERIAL:
            serial_port_vo = SerialPortProfile.create(port=serial_port, baud_rate=baud_rate)

        network_endpoint_vo = None
        if connection_type is ConnectionType.NETWORK:
            network_endpoint_vo = NetworkEndpoint.create(host=host, port=port)

        connection_profile = ConnectionProfile.create(
            connection_type, serial_port=serial_port_vo, network_endpoint=network_endpoint_vo,
        )

        capabilities: tuple[DeviceCapability, ...] = ()
        if device_type in SCALE_DEVICE_TYPES:
            capabilities = (DeviceCapability.create(DeviceCapabilityCode.WEIGH),)
        elif device_type in READER_DEVICE_TYPES:
            capabilities = (DeviceCapability.create(REQUIRED_CAPABILITY_BY_TYPE[device_type]),)
        elif device_type in CASH_DRAWER_DEVICE_TYPES:
            capabilities = (DeviceCapability.create(DeviceCapabilityCode.DRAWER_PULSE),)
        elif device_type in PAYMENT_TERMINAL_DEVICE_TYPES:
            capabilities = tuple(
                DeviceCapability.create(DeviceCapabilityCode(code)) for code in payment_capabilities
            )

        profile = DeviceProfile.create(
            name=name, device_type=device_type, connection_profile=connection_profile,
            manufacturer=manufacturer, model=model, capabilities=capabilities,
            paper_profile=paper_profile or None, protocol=protocol, driver_name=driver_name,
        )
        if device_type in PRINTER_DEVICE_TYPES:
            assert_valid_printer_profile(profile)
        elif device_type in SCALE_DEVICE_TYPES:
            assert_valid_scale_profile(profile)
        elif device_type in READER_DEVICE_TYPES:
            assert_valid_reader_profile(profile)
        elif device_type in CASH_DRAWER_DEVICE_TYPES:
            assert_valid_cash_drawer_profile(profile)
        elif device_type in PAYMENT_TERMINAL_DEVICE_TYPES:
            assert_valid_payment_terminal_profile(profile)
        self._profiles.save(profile)
        self._conn.commit()
        return profile


class RegisterDeviceUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._devices = SqliteDeviceRepository(connection)
        self._profiles = SqliteDeviceProfileRepository(connection)

    def execute(
        self, *, branch_id: str, profile_id: str, code: str, name: str, hardware_identifier: str = "",
        notes: str = "",
    ) -> Device:
        if self._profiles.get(profile_id) is None:
            raise DeviceProfileNotFoundError(f"Perfil de dispositivo {profile_id} no encontrado")
        identifier_vo = DeviceIdentifier.create(hardware_identifier) if hardware_identifier.strip() else None
        device = Device.create(
            branch_id=branch_id, profile_id=profile_id, code=code, name=name,
            hardware_identifier=identifier_vo, notes=notes,
        )
        self._devices.save(device)
        self._conn.commit()
        return device


class UpdateDeviceUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._devices = SqliteDeviceRepository(connection)

    def execute(self, *, device_id: str, name: str, notes: str) -> Device:
        device = self._devices.get(device_id)
        if device is None:
            raise DeviceNotFoundError(f"Dispositivo {device_id} no encontrado")
        device.rename(name)
        device.update_notes(notes)
        self._devices.save(device)
        self._conn.commit()
        return device


class ChangeDeviceStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._devices = SqliteDeviceRepository(connection)

    def execute(self, *, device_id: str, action: DeviceStatusAction, reason: str = "") -> Device:
        device = self._devices.get(device_id)
        if device is None:
            raise DeviceNotFoundError(f"Dispositivo {device_id} no encontrado")

        if action is DeviceStatusAction.ACTIVATE:
            device.activate()
        elif action is DeviceStatusAction.DEACTIVATE:
            device.deactivate()
        elif action is DeviceStatusAction.BLOCK:
            device.block(reason)
        elif action is DeviceStatusAction.UNBLOCK:
            device.unblock()
        elif action is DeviceStatusAction.RETIRE:
            device.retire()

        self._devices.save(device)
        self._conn.commit()
        return device
