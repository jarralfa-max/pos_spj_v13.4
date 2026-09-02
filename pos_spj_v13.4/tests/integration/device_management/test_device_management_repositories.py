"""SET-7 — Device Management infrastructure repositories against a real
(in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.entities.workstation_device_assignment import (
    WorkstationDeviceAssignment,
)
from backend.domain.device_management.enums import (
    AssignmentRole,
    ConnectionType,
    DeviceCapabilityCode,
    DeviceType,
)
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.device_capability import DeviceCapability
from backend.domain.device_management.value_objects.device_identifier import DeviceIdentifier
from backend.domain.device_management.value_objects.network_endpoint import NetworkEndpoint
from backend.domain.device_management.value_objects.serial_port_profile import SerialPortProfile
from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationType
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import (
    SqliteDeviceRepository,
)
from backend.infrastructure.db.repositories.device_management.workstation_device_assignment_repository import (
    SqliteWorkstationDeviceAssignmentRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import (
    SqliteWorkstationRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def profile_repo(conn):
    return SqliteDeviceProfileRepository(conn)


@pytest.fixture
def device_repo(conn):
    return SqliteDeviceRepository(conn)


@pytest.fixture
def assignment_repo(conn):
    return SqliteWorkstationDeviceAssignmentRepository(conn)


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    return branch_id


def _existing_workstation_id(conn, branch_id: str) -> str:
    workstation = Workstation.create(
        branch_id=branch_id, code=f"POS-{new_uuid()[:8]}", name="Caja", workstation_type=WorkstationType.POS,
    )
    SqliteWorkstationRepository(conn).save(workstation)
    return workstation.id


def _usb_printer_profile(profile_repo, conn) -> DeviceProfile:
    profile = DeviceProfile.create(
        name="Epson TM-T20III USB", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    profile_repo.save(profile)
    conn.commit()
    return profile


class TestDeviceProfileRepository:
    def test_round_trips_network_connection_capabilities_and_credential_reference(self, conn, profile_repo):
        profile = DeviceProfile.create(
            name="Epson TM-T20III red", device_type=DeviceType.THERMAL_PRINTER,
            connection_profile=ConnectionProfile.create(
                ConnectionType.NETWORK,
                network_endpoint=NetworkEndpoint.create(host="10.0.0.20", port=9100, use_tls=True),
                credential_reference="printer_admin_token",
                extra_parameters={"queue_name": "receipts"},
            ),
            manufacturer="Epson", model="TM-T20III", paper_profile="80MM", protocol="ESC/POS",
            driver_name="escpos_generic", timeout_seconds=10, retry_max_attempts=5,
            capabilities=(
                DeviceCapability.create(DeviceCapabilityCode.CUT),
                DeviceCapability.create(DeviceCapabilityCode.DRAWER_PULSE),
            ),
        )
        profile_repo.save(profile)
        conn.commit()

        fetched = profile_repo.get(profile.id)
        assert fetched.connection_profile.network_endpoint.host == "10.0.0.20"
        assert fetched.connection_profile.network_endpoint.use_tls is True
        assert fetched.connection_profile.credential_reference == "printer_admin_token"
        assert fetched.connection_profile.extra_parameters == {"queue_name": "receipts"}
        assert fetched.has_capability(DeviceCapabilityCode.CUT)
        assert fetched.has_capability(DeviceCapabilityCode.DRAWER_PULSE)
        assert fetched.paper_profile == "80MM"
        assert fetched.timeout_seconds == 10
        assert fetched.retry_max_attempts == 5

    def test_round_trips_serial_connection(self, conn, profile_repo):
        profile = DeviceProfile.create(
            name="Toledo 8217", device_type=DeviceType.SCALE,
            connection_profile=ConnectionProfile.create(
                ConnectionType.SERIAL,
                serial_port=SerialPortProfile.create(
                    port="COM3", baud_rate=9600, parity="E", data_bits=7,
                    stop_bits="2", read_timeout_seconds=Decimal("1.5"),
                ),
            ),
        )
        profile_repo.save(profile)
        conn.commit()

        fetched = profile_repo.get(profile.id)
        serial = fetched.connection_profile.serial_port
        assert serial.port == "COM3"
        assert serial.baud_rate == 9600
        assert serial.parity == "E"
        assert serial.data_bits == 7
        assert serial.stop_bits == "2"
        assert serial.read_timeout_seconds == Decimal("1.5")

    def test_profile_without_capabilities_round_trips_empty_tuple(self, conn, profile_repo):
        profile = _usb_printer_profile(profile_repo, conn)
        assert profile_repo.get(profile.id).capabilities == ()

    def test_list_active_excludes_inactive(self, conn, profile_repo):
        active = _usb_printer_profile(profile_repo, conn)
        inactive = DeviceProfile.create(
            name="Impresora vieja", device_type=DeviceType.THERMAL_PRINTER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
        )
        inactive.deactivate()
        profile_repo.save(inactive)
        conn.commit()
        results = profile_repo.list_active()
        assert [p.id for p in results] == [active.id]


class TestDeviceRepository:
    def test_round_trips_all_fields(self, conn, device_repo, profile_repo):
        branch_id = _existing_branch_id(conn)
        profile = _usb_printer_profile(profile_repo, conn)
        device = Device.create(
            branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora caja 1",
            hardware_identifier=DeviceIdentifier.create("USB-SN-999"), notes="Instalada 2026-08-21",
        )
        device_repo.save(device)
        conn.commit()

        fetched = device_repo.get(device.id)
        assert fetched.branch_id == branch_id
        assert fetched.profile_id == profile.id
        assert fetched.hardware_identifier.value == "USB-SN-999"
        assert fetched.notes == "Instalada 2026-08-21"

    def test_profile_id_must_reference_existing_profile(self, conn, device_repo):
        branch_id = _existing_branch_id(conn)
        orphan = Device.create(branch_id=branch_id, profile_id=new_uuid(), code="PRN-99", name="Fantasma")
        with pytest.raises(sqlite3.IntegrityError):
            device_repo.save(orphan)
            conn.commit()
        conn.rollback()

    def test_branch_id_must_reference_existing_sucursal(self, conn, device_repo, profile_repo):
        profile = _usb_printer_profile(profile_repo, conn)
        orphan = Device.create(branch_id=new_uuid(), profile_id=profile.id, code="PRN-99", name="Fantasma")
        with pytest.raises(sqlite3.IntegrityError):
            device_repo.save(orphan)
            conn.commit()
        conn.rollback()

    def test_code_uniqueness_enforced(self, conn, device_repo, profile_repo):
        branch_id = _existing_branch_id(conn)
        profile = _usb_printer_profile(profile_repo, conn)
        device_repo.save(Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="A"))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            device_repo.save(Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="B"))
            conn.commit()
        conn.rollback()

    def test_get_by_code(self, conn, device_repo, profile_repo):
        branch_id = _existing_branch_id(conn)
        profile = _usb_printer_profile(profile_repo, conn)
        device = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="A")
        device_repo.save(device)
        conn.commit()
        assert device_repo.get_by_code("PRN-01").id == device.id
        assert device_repo.get_by_code("MISSING") is None

    def test_list_by_branch_and_list_active(self, conn, device_repo, profile_repo):
        branch_id_a, branch_id_b = _existing_branch_id(conn), _existing_branch_id(conn)
        profile = _usb_printer_profile(profile_repo, conn)
        active = Device.create(branch_id=branch_id_a, profile_id=profile.id, code="PRN-01", name="Activa")
        retired = Device.create(branch_id=branch_id_a, profile_id=profile.id, code="PRN-02", name="Retirada")
        retired.retire()
        other_branch = Device.create(branch_id=branch_id_b, profile_id=profile.id, code="PRN-03", name="Otra sucursal")
        device_repo.save(active)
        device_repo.save(retired)
        device_repo.save(other_branch)
        conn.commit()

        assert {d.code for d in device_repo.list_by_branch(branch_id_a)} == {"PRN-01", "PRN-02"}
        # list_active() has no branch filter (matches its Protocol
        # signature) — it's every ACTIVE device system-wide, so the
        # other-branch device (still ACTIVE, never retired) belongs here too.
        assert {d.code for d in device_repo.list_active()} == {"PRN-01", "PRN-03"}


class TestWorkstationDeviceAssignmentRepository:
    def test_round_trips_and_conflict_enforced(self, conn, device_repo, profile_repo, assignment_repo):
        branch_id = _existing_branch_id(conn)
        workstation_id = _existing_workstation_id(conn, branch_id)
        profile = _usb_printer_profile(profile_repo, conn)
        device_a = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="A")
        device_b = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-02", name="B")
        device_repo.save(device_a)
        device_repo.save(device_b)
        conn.commit()

        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=workstation_id, device_id=device_a.id,
            role=AssignmentRole.PRIMARY_RECEIPT_PRINTER, assigned_by_user_id="admin-1",
        )
        assignment_repo.save(assignment)
        conn.commit()

        fetched = assignment_repo.get_active_for_role(workstation_id, AssignmentRole.PRIMARY_RECEIPT_PRINTER)
        assert fetched.device_id == device_a.id
        assert fetched.assigned_by_user_id == "admin-1"

        conflicting = WorkstationDeviceAssignment.assign(
            workstation_id=workstation_id, device_id=device_b.id, role=AssignmentRole.PRIMARY_RECEIPT_PRINTER,
        )
        with pytest.raises(sqlite3.IntegrityError):
            assignment_repo.save(conflicting)
            conn.commit()
        conn.rollback()

    def test_unassign_then_reassign_a_different_device_to_the_same_role(
        self, conn, device_repo, profile_repo, assignment_repo,
    ):
        branch_id = _existing_branch_id(conn)
        workstation_id = _existing_workstation_id(conn, branch_id)
        profile = _usb_printer_profile(profile_repo, conn)
        device_a = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="A")
        device_b = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-02", name="B")
        device_repo.save(device_a)
        device_repo.save(device_b)
        conn.commit()

        first = WorkstationDeviceAssignment.assign(
            workstation_id=workstation_id, device_id=device_a.id, role=AssignmentRole.SCALE,
        )
        assignment_repo.save(first)
        conn.commit()

        first.unassign()
        assignment_repo.save(first)
        conn.commit()

        second = WorkstationDeviceAssignment.assign(
            workstation_id=workstation_id, device_id=device_b.id, role=AssignmentRole.SCALE,
        )
        assignment_repo.save(second)
        conn.commit()

        active = assignment_repo.get_active_for_role(workstation_id, AssignmentRole.SCALE)
        assert active.device_id == device_b.id
        assert assignment_repo.list_active_for_workstation(workstation_id) == [active]

    def test_list_for_device_includes_inactive_history(self, conn, device_repo, profile_repo, assignment_repo):
        branch_id = _existing_branch_id(conn)
        workstation_id = _existing_workstation_id(conn, branch_id)
        profile = _usb_printer_profile(profile_repo, conn)
        device = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="A")
        device_repo.save(device)
        conn.commit()

        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=workstation_id, device_id=device.id, role=AssignmentRole.CASH_DRAWER,
        )
        assignment_repo.save(assignment)
        conn.commit()
        assignment.unassign()
        assignment_repo.save(assignment)
        conn.commit()

        history = assignment_repo.list_for_device(device.id)
        assert len(history) == 1
        assert history[0].active is False

    def test_device_id_must_reference_existing_device(self, conn, assignment_repo):
        branch_id = _existing_branch_id(conn)
        workstation_id = _existing_workstation_id(conn, branch_id)
        orphan = WorkstationDeviceAssignment.assign(
            workstation_id=workstation_id, device_id=new_uuid(), role=AssignmentRole.SCALE,
        )
        with pytest.raises(sqlite3.IntegrityError):
            assignment_repo.save(orphan)
            conn.commit()
        conn.rollback()
