from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CashDeviceRow:
    id: str
    name: str
    branch_name: str
    assignment: str
    status: str
    hardware_status: str


class DeviceReadRepository(Protocol):
    def list_devices(self, kind: str) -> list[dict]: ...


class CashDeviceQueryService:
    def __init__(self, repository: DeviceReadRepository): self._repository = repository

    def list_devices(self, kind: str) -> list[CashDeviceRow]:
        if kind not in {"register", "drawer", "terminal"}: raise ValueError("Unknown device kind")
        return [CashDeviceRow(str(row["id"]), str(row["name"]),
                              str(row.get("branch_name", row.get("branch_id", ""))),
                              str(row.get("assignment", "")), str(row["status"]),
                              str(row.get("hardware_status", "No verificado")))
                for row in self._repository.list_devices(kind)]
