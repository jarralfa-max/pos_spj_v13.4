from dataclasses import dataclass
from typing import Protocol

from backend.shared.ids import is_uuidv7


@dataclass(frozen=True, slots=True)
class CashDeviceRow:
    id: str
    name: str
    branch_name: str
    assignment: str
    status: str
    hardware_status: str


class DeviceReadRepository(Protocol):
    def list_devices(self, kind: str, branch_id: str | None = None) -> list[dict]: ...


class CashDeviceQueryService:
    def __init__(self, repository: DeviceReadRepository): self._repository = repository

    def list_devices(self, kind: str, *, branch_id: str | None = None) -> list[CashDeviceRow]:
        """Dispositivos de un tipo, acotados a `branch_id` cuando se indica.

        Sin acotar se listan todos, y eso es una trampa para cualquier pantalla
        que ofrezca acciones: `SetCashDeviceStatusUseCase` exige que el
        dispositivo pertenezca a la sucursal del actor y lanza `LookupError`
        —"Dispositivo no encontrado o fuera de alcance"— para cualquier otro.
        Listar de mas significa ofrecer botones que el backend rechaza siempre.
        """
        if kind not in {"register", "drawer", "terminal"}: raise ValueError("Unknown device kind")
        rows: list[CashDeviceRow] = []
        for row in self._repository.list_devices(kind, branch_id):
            device_id = str(row["id"])
            hardware_status = str(row.get("hardware_status", "No verificado"))
            if not is_uuidv7(device_id):
                hardware_status = "Identidad inválida"
            rows.append(
                CashDeviceRow(device_id, str(row["name"]),
                              str(row.get("branch_name", row.get("branch_id", ""))),
                              str(row.get("assignment", "")), str(row["status"]),
                              hardware_status)
            )
        return rows
