from __future__ import annotations

from typing import Dict, Iterable


class InventoryAvailabilityService:
    """
    Fuente única de disponibilidad para venta:
      disponible_para_venta = stock_fisico - reservas_activas
    """

    def __init__(self, stock_reservation_service):
        self._reservations = stock_reservation_service

    def disponible_para_venta(self, producto_id: int) -> float:
        return float(self._reservations.stock_disponible(str(producto_id)))

    def disponible_por_producto(self, producto_ids: Iterable[int]) -> Dict[int, float]:
        out: Dict[int, float] = {}
        for pid in producto_ids:
            out[int(pid)] = self.disponible_para_venta(int(pid))
        return out

