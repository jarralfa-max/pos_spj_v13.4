"""DeliveryZonesQueryService — las zonas de entrega de una sucursal, activas e
inactivas, para la pantalla de Configuración.

`DeliveryZoneRepository.list_active_for_branch` sólo devuelve las activas (es lo
que necesita la resolución de domicilios); una pantalla de configuración tiene
que enseñar también las desactivadas, o no habría forma de reactivarlas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeliveryZoneRow:
    id: str
    name: str
    postal_codes: tuple[str, ...]
    minimum_order: str
    delivery_fee: str
    free_delivery_threshold: str | None
    estimated_minutes: int | None
    maximum_distance_km: str | None
    active: bool


class DeliveryZonesQueryService:
    def __init__(self, db) -> None:
        self.db = db

    def list_for_branch(self, branch_id: str) -> list[DeliveryZoneRow]:
        """Activas primero, luego por nombre."""
        filas = self.db.execute(
            "SELECT id, name, postal_codes_json, minimum_order, delivery_fee,"
            " free_delivery_threshold, estimated_minutes, maximum_distance_km, active"
            " FROM delivery_zones WHERE branch_id=?"
            " ORDER BY active DESC, name COLLATE NOCASE, id",
            (branch_id,)).fetchall()
        return [
            DeliveryZoneRow(
                id=fila[0], name=fila[1], postal_codes=tuple(json.loads(fila[2] or "[]")),
                minimum_order=fila[3], delivery_fee=fila[4], free_delivery_threshold=fila[5],
                estimated_minutes=fila[6], maximum_distance_km=fila[7], active=bool(fila[8]))
            for fila in filas
        ]
