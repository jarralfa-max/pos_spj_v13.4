"""SET-10 — Cajones y terminales end to end against real SQLite: no new
migration was needed for this SET (see MIGRATION_LOG.md) — this proves
why: SET-7's `devices`/`device_profiles`/`workstation_device_assignments`
and SET-9's `device_test_results` already generalize to CASH_DRAWER and
PAYMENT_TERMINAL device types without any schema change.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.entities.device_test_result import DeviceTestResult
from backend.domain.device_management.entities.workstation_device_assignment import (
    WorkstationDeviceAssignment,
)
from backend.domain.device_management.enums import AssignmentRole, ConnectionType, DeviceCapabilityCode, DeviceType
from backend.domain.device_management.exceptions import CashDrawerOpeningNotAuthorizedError
from backend.domain.device_management.policies.cash_drawer_profile_policy import (
    assert_valid_cash_drawer_profile,
)
from backend.domain.device_management.policies.cash_drawer_security_policy import assert_can_open
from backend.domain.device_management.policies.payment_terminal_profile_policy import (
    assert_valid_payment_terminal_profile,
)
from backend.domain.device_management.value_objects.cash_drawer_open_request import CashDrawerOpenRequest
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.device_capability import DeviceCapability
from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationType
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import (
    SqliteDeviceRepository,
)
from backend.infrastructure.db.repositories.device_management.device_test_result_repository import (
    SqliteDeviceTestResultRepository,
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


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal"))
    return branch_id


class TestCashDrawerEndToEnd:
    def test_register_assign_test_and_authorize_open(self, conn):
        profile_repo = SqliteDeviceProfileRepository(conn)
        device_repo = SqliteDeviceRepository(conn)
        assignment_repo = SqliteWorkstationDeviceAssignmentRepository(conn)
        test_repo = SqliteDeviceTestResultRepository(conn)
        ws_repo = SqliteWorkstationRepository(conn)

        branch_id = _existing_branch_id(conn)
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
        )
        ws_repo.save(workstation)
        conn.commit()

        # Perfiles
        profile = DeviceProfile.create(
            name="MMF Cajón", device_type=DeviceType.CASH_DRAWER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
            capabilities=(DeviceCapability.create(DeviceCapabilityCode.DRAWER_PULSE),),
        )
        assert_valid_cash_drawer_profile(profile)
        profile_repo.save(profile)
        conn.commit()

        device = Device.create(branch_id=branch_id, profile_id=profile.id, code="DRAWER-01", name="Cajón caja 1")
        device_repo.save(device)
        conn.commit()

        # Asignación
        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=workstation.id, device_id=device.id, role=AssignmentRole.CASH_DRAWER,
            assigned_by_user_id="admin-1",
        )
        assignment_repo.save(assignment)
        conn.commit()
        assert assignment_repo.get_active_for_role(workstation.id, AssignmentRole.CASH_DRAWER).device_id == device.id

        # Pruebas
        test_result = DeviceTestResult.record(device_id=device.id, test_type="open_test", success=True, message="Pulso enviado")
        test_repo.save(test_result)
        conn.commit()
        assert test_repo.list_for_device(device.id)[0].test_type == "OPEN_TEST"

        # Seguridad
        authorized = CashDrawerOpenRequest.create(device_id=device.id, opened_by_user_id="cashier-1", sale_reference="SALE-001")
        assert_can_open(authorized)  # does not raise

        denied = CashDrawerOpenRequest.create(device_id=device.id, opened_by_user_id="cashier-1")
        with pytest.raises(CashDrawerOpeningNotAuthorizedError):
            assert_can_open(denied)


class TestPaymentTerminalEndToEnd:
    def test_register_assign_and_test(self, conn):
        profile_repo = SqliteDeviceProfileRepository(conn)
        device_repo = SqliteDeviceRepository(conn)
        assignment_repo = SqliteWorkstationDeviceAssignmentRepository(conn)
        test_repo = SqliteDeviceTestResultRepository(conn)
        ws_repo = SqliteWorkstationRepository(conn)

        branch_id = _existing_branch_id(conn)
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
        )
        ws_repo.save(workstation)
        conn.commit()

        profile = DeviceProfile.create(
            name="Clip Terminal", device_type=DeviceType.PAYMENT_TERMINAL,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
            capabilities=(DeviceCapability.create(DeviceCapabilityCode.CARD_CONTACTLESS),),
        )
        assert_valid_payment_terminal_profile(profile)
        profile_repo.save(profile)
        conn.commit()

        device = Device.create(branch_id=branch_id, profile_id=profile.id, code="TERM-01", name="Terminal caja 1")
        device_repo.save(device)
        conn.commit()

        assignment = WorkstationDeviceAssignment.assign(
            workstation_id=workstation.id, device_id=device.id, role=AssignmentRole.PAYMENT_TERMINAL,
        )
        assignment_repo.save(assignment)
        conn.commit()
        assert assignment_repo.get_active_for_role(workstation.id, AssignmentRole.PAYMENT_TERMINAL).device_id == device.id

        test_result = DeviceTestResult.record(device_id=device.id, test_type="connectivity", success=True)
        test_repo.save(test_result)
        conn.commit()
        assert test_repo.list_for_device(device.id)[0].success is True

    def test_conflicting_active_assignment_still_enforced_for_these_roles(self, conn):
        # Reuses SET-7's partial unique index — confirms it applies here
        # too, not just to printers/scales.
        profile_repo = SqliteDeviceProfileRepository(conn)
        device_repo = SqliteDeviceRepository(conn)
        assignment_repo = SqliteWorkstationDeviceAssignmentRepository(conn)
        ws_repo = SqliteWorkstationRepository(conn)

        branch_id = _existing_branch_id(conn)
        workstation = Workstation.create(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
        )
        ws_repo.save(workstation)
        conn.commit()

        profile = DeviceProfile.create(
            name="Cajón genérico", device_type=DeviceType.CASH_DRAWER,
            connection_profile=ConnectionProfile.create(ConnectionType.USB),
            capabilities=(DeviceCapability.create(DeviceCapabilityCode.DRAWER_PULSE),),
        )
        profile_repo.save(profile)
        conn.commit()

        device_a = Device.create(branch_id=branch_id, profile_id=profile.id, code="DRAWER-01", name="A")
        device_b = Device.create(branch_id=branch_id, profile_id=profile.id, code="DRAWER-02", name="B")
        device_repo.save(device_a)
        device_repo.save(device_b)
        conn.commit()

        assignment_repo.save(WorkstationDeviceAssignment.assign(
            workstation_id=workstation.id, device_id=device_a.id, role=AssignmentRole.CASH_DRAWER,
        ))
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            assignment_repo.save(WorkstationDeviceAssignment.assign(
                workstation_id=workstation.id, device_id=device_b.id, role=AssignmentRole.CASH_DRAWER,
            ))
            conn.commit()
        conn.rollback()
