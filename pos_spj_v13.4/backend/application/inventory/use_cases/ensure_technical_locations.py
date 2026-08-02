"""EnsureTechnicalLocationsUseCase (§8) — canonical technical locations per warehouse.

Creates one real ``storage_locations`` row (its own UUIDv7) per technical location
type (RECEIVING/AVAILABLE/PICKING/QUARANTINE/DAMAGED/TRANSIT/RETURNS/PRODUCTION) for
a warehouse, so the stock engine addresses these instead of using ``warehouse_id``
as if it were a physical location. Idempotent by ``(warehouse_id, code)``.
"""

from __future__ import annotations

from backend.domain.inventory.enums import TechnicalLocationType
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.shared.ids import new_uuid

#: Stable per-warehouse code for each technical location type.
_CODE_PREFIX = "TECH"

_NAME_ES = {
    TechnicalLocationType.RECEIVING: "Recepción",
    TechnicalLocationType.AVAILABLE: "Disponible",
    TechnicalLocationType.PICKING: "Surtido",
    TechnicalLocationType.QUARANTINE: "Cuarentena",
    TechnicalLocationType.DAMAGED: "Dañado",
    TechnicalLocationType.TRANSIT: "En tránsito",
    TechnicalLocationType.RETURNS: "Devoluciones",
    TechnicalLocationType.PRODUCTION: "Producción",
}


def technical_code(location_type: TechnicalLocationType) -> str:
    return f"{_CODE_PREFIX}:{location_type.value}"


class EnsureTechnicalLocationsUseCase:
    """Idempotently seed the canonical technical locations for a warehouse (§8)."""

    def execute(self, connection, *, warehouse_id: str) -> dict[str, str]:
        if not warehouse_id:
            raise ValueError("warehouse_id requerido para ubicaciones técnicas")
        result: dict[str, str] = {}
        with InventoryUnitOfWork(connection) as uow:
            for loc_type in TechnicalLocationType:
                code = technical_code(loc_type)
                existing = uow.warehouses.get_location_by_code(warehouse_id, code)
                if existing is not None:
                    result[loc_type.value] = existing["id"]
                    continue
                location_id = new_uuid()
                uow.warehouses.save_technical_location(
                    location_id=location_id, warehouse_id=warehouse_id, code=code,
                    name=_NAME_ES[loc_type], location_type=loc_type.value)
                result[loc_type.value] = location_id
        return result
