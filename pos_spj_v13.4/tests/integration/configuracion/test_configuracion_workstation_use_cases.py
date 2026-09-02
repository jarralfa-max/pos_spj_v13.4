"""SET-6 follow-up — real CRUD for "Estaciones" (General): register a
workstation, edit it, and drive its full 7-transition lifecycle. Against
a real (in-memory) SQLite born-clean schema. Mirrors
`test_configuracion_device_management_use_cases.py`'s shape.
"""

from __future__ import annotations

import pytest

from backend.application.use_cases.configuracion.workstation_use_cases import (
    ChangeWorkstationStatusUseCase,
    RegisterWorkstationUseCase,
    UpdateWorkstationUseCase,
    WorkstationStatusAction,
)
from backend.domain.settings.enums import WorkstationStatus, WorkstationType
from backend.domain.settings.exceptions import (
    ConfigurationInvalidValueError,
    WorkstationNotFoundError,
    WorkstationTransitionNotAllowedError,
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
def branch_id(conn):
    existing = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()
    if existing:
        return existing[0]
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal Test"))
    conn.commit()
    return branch_id


class TestRegisterWorkstationUseCase:
    def test_registers_a_workstation(self, conn, branch_id):
        use_case = RegisterWorkstationUseCase(conn)
        workstation = use_case.execute(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type="POS",
            device_identifier="SN-001", operating_system="Windows 11",
        )
        assert workstation.status is WorkstationStatus.ACTIVE
        fetched = SqliteWorkstationRepository(conn).get(workstation.id)
        assert fetched.code == "POS-01"
        assert fetched.workstation_type is WorkstationType.POS

    def test_accepts_string_or_enum_for_workstation_type(self, conn, branch_id):
        use_case = RegisterWorkstationUseCase(conn)
        workstation = use_case.execute(
            branch_id=branch_id, code="WH-01", name="Almacén 1",
            workstation_type=WorkstationType.WAREHOUSE,
        )
        assert workstation.workstation_type is WorkstationType.WAREHOUSE

    def test_rejects_blank_code(self, conn, branch_id):
        use_case = RegisterWorkstationUseCase(conn)
        with pytest.raises(ConfigurationInvalidValueError):
            use_case.execute(branch_id=branch_id, code="  ", name="Caja 1", workstation_type="POS")


class TestUpdateWorkstationUseCase:
    def test_updates_name_identifier_and_os(self, conn, branch_id):
        workstation = RegisterWorkstationUseCase(conn).execute(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type="POS",
        )
        use_case = UpdateWorkstationUseCase(conn)
        updated = use_case.execute(
            workstation_id=workstation.id, name="Caja 1 (mostrador)", device_identifier="SN-002",
            operating_system="Windows 11",
        )
        assert updated.name == "Caja 1 (mostrador)"
        assert updated.device_identifier == "SN-002"
        assert updated.operating_system == "Windows 11"

    def test_unknown_workstation_raises(self, conn):
        use_case = UpdateWorkstationUseCase(conn)
        with pytest.raises(WorkstationNotFoundError):
            use_case.execute(workstation_id=new_uuid(), name="X")


class TestChangeWorkstationStatusUseCase:
    def _workstation(self, conn, branch_id):
        return RegisterWorkstationUseCase(conn).execute(
            branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type="POS",
        )

    def test_full_lifecycle(self, conn, branch_id):
        workstation = self._workstation(conn, branch_id)
        use_case = ChangeWorkstationStatusUseCase(conn)

        maintenance = use_case.execute(
            workstation_id=workstation.id, action=WorkstationStatusAction.ENTER_MAINTENANCE,
        )
        assert maintenance.status is WorkstationStatus.MAINTENANCE

        active_again = use_case.execute(
            workstation_id=workstation.id, action=WorkstationStatusAction.EXIT_MAINTENANCE,
        )
        assert active_again.status is WorkstationStatus.ACTIVE

        blocked = use_case.execute(
            workstation_id=workstation.id, action=WorkstationStatusAction.BLOCK, reason="revisión",
        )
        assert blocked.status is WorkstationStatus.BLOCKED
        assert blocked.blocked_reason == "revisión"

        unblocked = use_case.execute(workstation_id=workstation.id, action=WorkstationStatusAction.UNBLOCK)
        assert unblocked.status is WorkstationStatus.ACTIVE

        deactivated = use_case.execute(
            workstation_id=workstation.id, action=WorkstationStatusAction.DEACTIVATE,
        )
        assert deactivated.status is WorkstationStatus.INACTIVE

        activated = use_case.execute(workstation_id=workstation.id, action=WorkstationStatusAction.ACTIVATE)
        assert activated.status is WorkstationStatus.ACTIVE

        retired = use_case.execute(workstation_id=workstation.id, action=WorkstationStatusAction.RETIRE)
        assert retired.status is WorkstationStatus.RETIRED

    def test_retired_is_terminal(self, conn, branch_id):
        workstation = self._workstation(conn, branch_id)
        use_case = ChangeWorkstationStatusUseCase(conn)
        use_case.execute(workstation_id=workstation.id, action=WorkstationStatusAction.RETIRE)
        with pytest.raises(WorkstationTransitionNotAllowedError):
            use_case.execute(workstation_id=workstation.id, action=WorkstationStatusAction.ACTIVATE)

    def test_block_requires_a_reason(self, conn, branch_id):
        workstation = self._workstation(conn, branch_id)
        use_case = ChangeWorkstationStatusUseCase(conn)
        with pytest.raises(ConfigurationInvalidValueError):
            use_case.execute(workstation_id=workstation.id, action=WorkstationStatusAction.BLOCK, reason="   ")

    def test_unknown_workstation_raises(self, conn):
        use_case = ChangeWorkstationStatusUseCase(conn)
        with pytest.raises(WorkstationNotFoundError):
            use_case.execute(workstation_id=new_uuid(), action=WorkstationStatusAction.ACTIVATE)
