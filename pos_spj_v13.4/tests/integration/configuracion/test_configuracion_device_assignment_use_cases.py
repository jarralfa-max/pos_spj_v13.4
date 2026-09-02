"""SET-7 follow-up — real CRUD for "Asignaciones" (device ↔ workstation
role), the fourth pillar of Device Management (Devices/Profiles closed
by the Dispositivos round; Assignments closed here). Against a real
(in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import pytest

from backend.application.use_cases.configuracion.device_assignment_use_cases import (
    AssignDeviceUseCase,
    UnassignDeviceUseCase,
)
from backend.application.use_cases.configuracion.workstation_use_cases import RegisterWorkstationUseCase
from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import AssignmentRole, ConnectionType, DeviceType
from backend.domain.device_management.exceptions import (
    DeviceAssignmentConflictError,
    DeviceAssignmentNotFoundError,
    DeviceAssignmentRoleNotCompatibleError,
    DeviceNotFoundError,
)
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository
from backend.infrastructure.db.repositories.device_management.workstation_device_assignment_repository import (
    SqliteWorkstationDeviceAssignmentRepository,
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


@pytest.fixture
def workstation_id(conn, branch_id):
    workstation = RegisterWorkstationUseCase(conn).execute(
        branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type="POS",
    )
    return workstation.id


def _saved_printer(conn, branch_id) -> Device:
    profile = DeviceProfile.create(
        name="Epson TM-T20III", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code="PRN-01", name="Impresora 1")
    SqliteDeviceRepository(conn).save(device)
    conn.commit()
    return device


def _saved_scale(conn, branch_id) -> Device:
    profile = DeviceProfile.create(
        name="Bascula Toledo", device_type=DeviceType.SCALE,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code="SCL-01", name="Báscula 1")
    SqliteDeviceRepository(conn).save(device)
    conn.commit()
    return device


class TestAssignDeviceUseCase:
    def test_assigns_a_compatible_device(self, conn, branch_id, workstation_id):
        printer = _saved_printer(conn, branch_id)
        use_case = AssignDeviceUseCase(conn)
        assignment = use_case.execute(
            workstation_id=workstation_id, device_id=printer.id,
            role=AssignmentRole.PRIMARY_RECEIPT_PRINTER, assigned_by_user_id="admin-1",
        )
        assert assignment.active is True
        fetched = SqliteWorkstationDeviceAssignmentRepository(conn).get(assignment.id)
        assert fetched.device_id == printer.id
        assert fetched.role is AssignmentRole.PRIMARY_RECEIPT_PRINTER

    def test_rejects_role_incompatible_device_type(self, conn, branch_id, workstation_id):
        scale = _saved_scale(conn, branch_id)
        use_case = AssignDeviceUseCase(conn)
        with pytest.raises(DeviceAssignmentRoleNotCompatibleError):
            use_case.execute(
                workstation_id=workstation_id, device_id=scale.id,
                role=AssignmentRole.PRIMARY_RECEIPT_PRINTER,
            )

    def test_rejects_a_second_active_assignment_for_the_same_role(self, conn, branch_id, workstation_id):
        printer1 = _saved_printer(conn, branch_id)
        profile2 = DeviceProfile.create(
            name="Epson TM-T20III (2)", device_type=DeviceType.THERMAL_PRINTER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
        )
        SqliteDeviceProfileRepository(conn).save(profile2)
        printer2 = Device.create(
            branch_id=branch_id, profile_id=profile2.id, code="PRN-02", name="Impresora 2",
        )
        SqliteDeviceRepository(conn).save(printer2)
        conn.commit()

        use_case = AssignDeviceUseCase(conn)
        use_case.execute(
            workstation_id=workstation_id, device_id=printer1.id,
            role=AssignmentRole.PRIMARY_RECEIPT_PRINTER,
        )
        with pytest.raises(DeviceAssignmentConflictError):
            use_case.execute(
                workstation_id=workstation_id, device_id=printer2.id,
                role=AssignmentRole.PRIMARY_RECEIPT_PRINTER,
            )

    def test_allows_reassignment_after_unassign(self, conn, branch_id, workstation_id):
        printer1 = _saved_printer(conn, branch_id)
        profile2 = DeviceProfile.create(
            name="Epson TM-T20III (2)", device_type=DeviceType.THERMAL_PRINTER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
        )
        SqliteDeviceProfileRepository(conn).save(profile2)
        printer2 = Device.create(
            branch_id=branch_id, profile_id=profile2.id, code="PRN-02", name="Impresora 2",
        )
        SqliteDeviceRepository(conn).save(printer2)
        conn.commit()

        assign_uc = AssignDeviceUseCase(conn)
        first = assign_uc.execute(
            workstation_id=workstation_id, device_id=printer1.id,
            role=AssignmentRole.PRIMARY_RECEIPT_PRINTER,
        )
        UnassignDeviceUseCase(conn).execute(assignment_id=first.id)
        second = assign_uc.execute(
            workstation_id=workstation_id, device_id=printer2.id,
            role=AssignmentRole.PRIMARY_RECEIPT_PRINTER,
        )
        assert second.device_id == printer2.id

    def test_rejects_an_unknown_device(self, conn, workstation_id):
        use_case = AssignDeviceUseCase(conn)
        with pytest.raises(DeviceNotFoundError):
            use_case.execute(
                workstation_id=workstation_id, device_id=new_uuid(),
                role=AssignmentRole.PRIMARY_RECEIPT_PRINTER,
            )

    def test_accepts_string_role(self, conn, branch_id, workstation_id):
        printer = _saved_printer(conn, branch_id)
        use_case = AssignDeviceUseCase(conn)
        assignment = use_case.execute(
            workstation_id=workstation_id, device_id=printer.id, role="PRIMARY_RECEIPT_PRINTER",
        )
        assert assignment.role is AssignmentRole.PRIMARY_RECEIPT_PRINTER


class TestUnassignDeviceUseCase:
    def test_unassigns_an_active_assignment(self, conn, branch_id, workstation_id):
        printer = _saved_printer(conn, branch_id)
        assignment = AssignDeviceUseCase(conn).execute(
            workstation_id=workstation_id, device_id=printer.id,
            role=AssignmentRole.PRIMARY_RECEIPT_PRINTER,
        )
        use_case = UnassignDeviceUseCase(conn)
        unassigned = use_case.execute(assignment_id=assignment.id)
        assert unassigned.active is False
        assert SqliteWorkstationDeviceAssignmentRepository(conn).get_active_for_role(
            workstation_id, AssignmentRole.PRIMARY_RECEIPT_PRINTER,
        ) is None

    def test_unknown_assignment_raises(self, conn):
        use_case = UnassignDeviceUseCase(conn)
        with pytest.raises(DeviceAssignmentNotFoundError):
            use_case.execute(assignment_id=new_uuid())
