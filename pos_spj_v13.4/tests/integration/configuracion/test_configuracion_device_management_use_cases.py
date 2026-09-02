"""SET-25 follow-up — real CRUD for "Dispositivos": register a device
profile, register a device, edit it, and drive its full lifecycle. Against
a real (in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import pytest

from backend.application.use_cases.configuracion.device_management_use_cases import (
    ChangeDeviceStatusUseCase,
    DeviceStatusAction,
    RegisterDeviceProfileUseCase,
    RegisterDeviceUseCase,
    UpdateDeviceUseCase,
)
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import ConnectionType, DeviceCapabilityCode, DeviceStatus, DeviceType
from backend.domain.device_management.exceptions import (
    DeviceNotFoundError,
    DeviceProfileNotFoundError,
    DeviceTransitionNotAllowedError,
    InvalidPaymentTerminalProfileError,
    InvalidPrinterProfileError,
    InvalidReaderProfileError,
    InvalidScaleProfileError,
)
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import (
    SqliteDeviceRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def branch_id(conn):
    existing = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()
    if existing:
        return existing[0]
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal Test"))
    conn.commit()
    return branch_id


def _saved_profile(conn) -> DeviceProfile:
    profile = DeviceProfile.create(
        name="Epson TM-T20III", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    conn.commit()
    return profile


class TestRegisterDeviceProfileUseCase:
    def test_registers_a_usb_profile(self, conn):
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(
            name="Epson TM-T20III", device_type="THERMAL_PRINTER", connection_type="USB",
            manufacturer="Epson", model="TM-T20III",
        )
        assert profile.device_type is DeviceType.THERMAL_PRINTER
        fetched = SqliteDeviceProfileRepository(conn).get(profile.id)
        assert fetched.name == "Epson TM-T20III"

    def test_registers_a_serial_profile_with_port_and_baud_rate(self, conn):
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(
            name="Bascula Toledo", device_type="SCALE", connection_type="SERIAL", serial_port="COM3",
            baud_rate=9600,
        )
        assert profile.connection_profile.serial_port.port == "COM3"
        assert profile.connection_profile.serial_port.baud_rate == 9600

    def test_registers_a_network_profile_with_host_and_port(self, conn):
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(
            name="Impresora de red", device_type="THERMAL_PRINTER", connection_type="NETWORK",
            host="192.168.1.50", port=9100,
        )
        assert profile.connection_profile.network_endpoint.host == "192.168.1.50"
        assert profile.connection_profile.network_endpoint.port == 9100

    def test_accepts_string_or_enum_for_device_type_and_connection_type(self, conn):
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(
            name="Cajón", device_type=DeviceType.CASH_DRAWER, connection_type=ConnectionType.USB,
        )
        assert profile.device_type is DeviceType.CASH_DRAWER

    def test_registers_a_printer_profile_with_paper_and_protocol(self, conn):
        # SET-8 follow-up: paper_profile/protocol are validated via
        # printer_profile_policy.assert_valid_printer_profile() when
        # device_type is one of the 4 printer types.
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(
            name="Epson TM-T20III", device_type="THERMAL_PRINTER", connection_type="USB",
            paper_profile="PAPER_80MM", protocol="ESC_POS",
        )
        assert profile.paper_profile == "PAPER_80MM"
        assert profile.protocol == "ESC_POS"

    def test_rejects_non_canonical_paper_profile_for_a_printer(self, conn):
        use_case = RegisterDeviceProfileUseCase(conn)
        with pytest.raises(InvalidPrinterProfileError):
            use_case.execute(
                name="Impresora", device_type="THERMAL_PRINTER", connection_type="USB",
                paper_profile="LETTER_SIZE_INVENTED",
            )

    def test_rejects_unrecognized_protocol_for_a_printer(self, conn):
        # §23: "no asumir que toda impresora es ESC/POS" — an unrecognized
        # protocol string is rejected, not silently accepted.
        use_case = RegisterDeviceProfileUseCase(conn)
        with pytest.raises(InvalidPrinterProfileError):
            use_case.execute(
                name="Impresora", device_type="THERMAL_PRINTER", connection_type="USB",
                protocol="SOME_MADE_UP_PROTOCOL",
            )

    def test_non_printer_device_type_skips_printer_validation(self, conn):
        # A SCALE profile with a (meaningless for it) paper_profile field
        # left blank must not trip printer-only validation at all.
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(name="Báscula", device_type="SCALE", connection_type="USB")
        assert profile.device_type is DeviceType.SCALE
        assert profile.paper_profile is None

    def test_registers_a_scale_profile_with_auto_weigh_capability(self, conn):
        # SET-9 follow-up: capabilities was always empty before this, so
        # no scale profile could ever pass its own policy (which requires
        # WEIGH). The required capability is derived from device_type,
        # never asked of the caller.
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(
            name="Bascula Toledo", device_type="SCALE", connection_type="SERIAL", serial_port="COM4",
            baud_rate=4800, protocol="TOLEDO_STANDARD",
        )
        assert profile.has_capability(DeviceCapabilityCode.WEIGH)
        assert profile.protocol == "TOLEDO_STANDARD"

    def test_rejects_a_printer_only_protocol_for_a_scale(self, conn):
        use_case = RegisterDeviceProfileUseCase(conn)
        with pytest.raises(InvalidScaleProfileError):
            use_case.execute(
                name="Bascula mala", device_type="SCALE", connection_type="USB", protocol="ESC_POS",
            )

    def test_registers_a_barcode_scanner_profile_with_auto_scan_1d_capability(self, conn):
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(name="Lector 1D", device_type="BARCODE_SCANNER", connection_type="USB")
        assert profile.has_capability(DeviceCapabilityCode.SCAN_1D)
        assert not profile.has_capability(DeviceCapabilityCode.SCAN_2D)

    def test_registers_a_qr_scanner_profile_with_auto_scan_2d_capability(self, conn):
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(name="Lector QR", device_type="QR_SCANNER", connection_type="USB")
        assert profile.has_capability(DeviceCapabilityCode.SCAN_2D)
        assert not profile.has_capability(DeviceCapabilityCode.SCAN_1D)

    def test_non_scale_non_reader_device_type_gets_no_capabilities(self, conn):
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(name="Otro", device_type="OTHER", connection_type="USB")
        assert profile.capabilities == ()

    def test_registers_a_cash_drawer_profile_with_auto_drawer_pulse_capability(self, conn):
        # SET-10 follow-up: same "capabilities was always empty" gap as
        # SET-9 — no cash drawer profile could ever pass
        # assert_valid_cash_drawer_profile() (requires DRAWER_PULSE)
        # before this. Deterministic from device_type, never asked of
        # the caller.
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(name="Cajon APG", device_type="CASH_DRAWER", connection_type="USB")
        assert profile.has_capability(DeviceCapabilityCode.DRAWER_PULSE)

    def test_registers_a_payment_terminal_profile_with_selected_capabilities(self, conn):
        # Unlike scales/readers/drawers, a payment terminal's capabilities
        # are a genuine choice (which payment methods it supports), so
        # the use case accepts them from the caller instead of deriving
        # them.
        use_case = RegisterDeviceProfileUseCase(conn)
        profile = use_case.execute(
            name="Terminal Clip", device_type="PAYMENT_TERMINAL", connection_type="NETWORK",
            host="192.168.1.60", port=8080, payment_capabilities=("CARD_CHIP", "CARD_CONTACTLESS"),
        )
        assert profile.has_capability(DeviceCapabilityCode.CARD_CHIP)
        assert profile.has_capability(DeviceCapabilityCode.CARD_CONTACTLESS)
        assert not profile.has_capability(DeviceCapabilityCode.CARD_SWIPE)

    def test_rejects_a_payment_terminal_profile_with_no_capabilities(self, conn):
        # §20: a terminal that can neither read a card nor accept/dispense
        # cash isn't a payment terminal.
        use_case = RegisterDeviceProfileUseCase(conn)
        with pytest.raises(InvalidPaymentTerminalProfileError):
            use_case.execute(name="Terminal vacía", device_type="PAYMENT_TERMINAL", connection_type="USB")


class TestRegisterDeviceUseCase:
    def test_registers_a_device_against_an_existing_profile(self, conn, branch_id):
        profile = _saved_profile(conn)
        use_case = RegisterDeviceUseCase(conn)
        device = use_case.execute(
            branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora caja 1",
            hardware_identifier="USB-SN-001", notes="Rollo 80mm",
        )
        assert device.status is DeviceStatus.ACTIVE
        fetched = SqliteDeviceRepository(conn).get(device.id)
        assert fetched.code == "PRN-01"

    def test_rejects_an_unknown_profile(self, conn, branch_id):
        use_case = RegisterDeviceUseCase(conn)
        with pytest.raises(DeviceProfileNotFoundError):
            use_case.execute(
                branch_id=branch_id, profile_id=new_uuid(), code="PRN-01", name="Impresora caja 1",
            )


class TestUpdateDeviceUseCase:
    def test_updates_name_and_notes(self, conn, branch_id):
        profile = _saved_profile(conn)
        device = RegisterDeviceUseCase(conn).execute(
            branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora caja 1",
        )
        use_case = UpdateDeviceUseCase(conn)
        updated = use_case.execute(device_id=device.id, name="Impresora caja 1 (v2)", notes="nueva nota")
        assert updated.name == "Impresora caja 1 (v2)"
        assert updated.notes == "nueva nota"

    def test_unknown_device_raises(self, conn):
        use_case = UpdateDeviceUseCase(conn)
        with pytest.raises(DeviceNotFoundError):
            use_case.execute(device_id=new_uuid(), name="X", notes="")


class TestChangeDeviceStatusUseCase:
    def _device(self, conn, branch_id):
        profile = _saved_profile(conn)
        return RegisterDeviceUseCase(conn).execute(
            branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora caja 1",
        )

    def test_full_lifecycle(self, conn, branch_id):
        device = self._device(conn, branch_id)
        use_case = ChangeDeviceStatusUseCase(conn)

        blocked = use_case.execute(device_id=device.id, action=DeviceStatusAction.BLOCK, reason="revision")
        assert blocked.status is DeviceStatus.BLOCKED
        assert blocked.blocked_reason == "revision"

        unblocked = use_case.execute(device_id=device.id, action=DeviceStatusAction.UNBLOCK)
        assert unblocked.status is DeviceStatus.ACTIVE

        deactivated = use_case.execute(device_id=device.id, action=DeviceStatusAction.DEACTIVATE)
        assert deactivated.status is DeviceStatus.INACTIVE

        activated = use_case.execute(device_id=device.id, action=DeviceStatusAction.ACTIVATE)
        assert activated.status is DeviceStatus.ACTIVE

        retired = use_case.execute(device_id=device.id, action=DeviceStatusAction.RETIRE)
        assert retired.status is DeviceStatus.RETIRED

    def test_retired_is_terminal(self, conn, branch_id):
        device = self._device(conn, branch_id)
        use_case = ChangeDeviceStatusUseCase(conn)
        use_case.execute(device_id=device.id, action=DeviceStatusAction.RETIRE)
        with pytest.raises(DeviceTransitionNotAllowedError):
            use_case.execute(device_id=device.id, action=DeviceStatusAction.ACTIVATE)

    def test_block_requires_a_reason(self, conn, branch_id):
        from backend.domain.device_management.exceptions import DeviceInvalidValueError

        device = self._device(conn, branch_id)
        use_case = ChangeDeviceStatusUseCase(conn)
        with pytest.raises(DeviceInvalidValueError):
            use_case.execute(device_id=device.id, action=DeviceStatusAction.BLOCK, reason="   ")

    def test_unknown_device_raises(self, conn):
        use_case = ChangeDeviceStatusUseCase(conn)
        with pytest.raises(DeviceNotFoundError):
            use_case.execute(device_id=new_uuid(), action=DeviceStatusAction.ACTIVATE)
