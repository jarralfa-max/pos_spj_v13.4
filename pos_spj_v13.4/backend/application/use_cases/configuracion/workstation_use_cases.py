"""Use cases for the "Estaciones" (General) section of the Configuración
workspace — SET-6's domain (`backend/domain/settings/entities/
workstation.py`) had zero UI before this round, same "domain done, zero
CRUD" gap already closed for Dispositivos/Documentos/Empresa. Thin
orchestration only — the state machine and its rules live entirely on
`Workstation` itself.

`ChangeWorkstationStatusUseCase` is deliberately ONE use case for all 7
transitions (activate/deactivate/enter_maintenance/exit_maintenance/
block/unblock/retire), same "one class, many actions" shape as
`device_management_use_cases.py::ChangeDeviceStatusUseCase` — `Device`
and `Workstation` share an (independently defined) identical 5-of-7-state
lifecycle shape.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationType
from backend.domain.settings.exceptions import WorkstationNotFoundError
from backend.infrastructure.db.repositories.settings.workstation_repository import (
    SqliteWorkstationRepository,
)


class WorkstationStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"
    ENTER_MAINTENANCE = "ENTER_MAINTENANCE"
    EXIT_MAINTENANCE = "EXIT_MAINTENANCE"
    BLOCK = "BLOCK"
    UNBLOCK = "UNBLOCK"
    RETIRE = "RETIRE"


class RegisterWorkstationUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._workstations = SqliteWorkstationRepository(connection)

    def execute(
        self, *, branch_id: str, code: str, name: str, workstation_type: WorkstationType | str,
        device_identifier: str = "", operating_system: str = "", offline_enabled: bool = True,
    ) -> Workstation:
        workstation = Workstation.create(
            branch_id=branch_id, code=code, name=name,
            workstation_type=WorkstationType(workstation_type),
            device_identifier=device_identifier, operating_system=operating_system,
            offline_enabled=offline_enabled,
        )
        self._workstations.save(workstation)
        self._conn.commit()
        return workstation


class UpdateWorkstationUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._workstations = SqliteWorkstationRepository(connection)

    def execute(
        self, *, workstation_id: str, name: str, device_identifier: str = "", operating_system: str = "",
    ) -> Workstation:
        workstation = self._workstations.get(workstation_id)
        if workstation is None:
            raise WorkstationNotFoundError(f"Estación {workstation_id} no encontrada")
        workstation.update_details(
            name=name, device_identifier=device_identifier, operating_system=operating_system,
        )
        self._workstations.save(workstation)
        self._conn.commit()
        return workstation


class ChangeWorkstationStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._workstations = SqliteWorkstationRepository(connection)

    def execute(
        self, *, workstation_id: str, action: WorkstationStatusAction, reason: str = "",
    ) -> Workstation:
        workstation = self._workstations.get(workstation_id)
        if workstation is None:
            raise WorkstationNotFoundError(f"Estación {workstation_id} no encontrada")

        if action is WorkstationStatusAction.ACTIVATE:
            workstation.activate()
        elif action is WorkstationStatusAction.DEACTIVATE:
            workstation.deactivate()
        elif action is WorkstationStatusAction.ENTER_MAINTENANCE:
            workstation.enter_maintenance()
        elif action is WorkstationStatusAction.EXIT_MAINTENANCE:
            workstation.exit_maintenance()
        elif action is WorkstationStatusAction.BLOCK:
            workstation.block(reason)
        elif action is WorkstationStatusAction.UNBLOCK:
            workstation.unblock()
        elif action is WorkstationStatusAction.RETIRE:
            workstation.retire()

        self._workstations.save(workstation)
        self._conn.commit()
        return workstation
