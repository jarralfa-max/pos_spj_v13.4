"""Cold-chain entities: TemperatureReading and TemperatureExcursion (§21).

A reading is a single temperature capture at a point (receipt/storage/dispatch/
transit); an excursion records a non-compliant reading and the action taken.
Inventory only records these facts — Quality decides release or disposal (§21).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import (
    ColdChainStatus,
    ExcursionAction,
    TemperaturePoint,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en temperatura")
    return Decimal(str(value))


@dataclass(slots=True)
class TemperatureReading:
    id: str
    sensor_id: str
    warehouse_id: str
    temperature: Decimal
    reading_point: TemperaturePoint
    status: ColdChainStatus = ColdChainStatus.COMPLIANT
    unit: str = "C"
    location_id: str | None = None
    lot_id: str | None = None
    captured_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, sensor_id: str, warehouse_id: str, temperature,
               reading_point: TemperaturePoint, **kwargs) -> "TemperatureReading":
        if not sensor_id or not warehouse_id:
            raise InventoryDomainError("La lectura requiere sensor y almacén")
        return cls(id=new_uuid(), sensor_id=sensor_id, warehouse_id=warehouse_id,
                   temperature=_dec(temperature), reading_point=reading_point, **kwargs)


@dataclass(slots=True)
class TemperatureExcursion:
    id: str
    reading_id: str
    warehouse_id: str
    status: ColdChainStatus
    temperature: Decimal
    min_temp: Decimal
    max_temp: Decimal
    action_taken: ExcursionAction = ExcursionAction.WARN
    lot_id: str | None = None
    resolved: bool = False
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, reading_id: str, warehouse_id: str, status: ColdChainStatus,
               temperature, min_temp, max_temp,
               action_taken: ExcursionAction = ExcursionAction.WARN,
               lot_id: str | None = None) -> "TemperatureExcursion":
        return cls(id=new_uuid(), reading_id=reading_id, warehouse_id=warehouse_id,
                   status=status, temperature=_dec(temperature), min_temp=_dec(min_temp),
                   max_temp=_dec(max_temp), action_taken=action_taken, lot_id=lot_id)
