from __future__ import annotations

from typing import Dict, Iterable, Optional


class InventoryAvailabilityService:
    """
    Fuente única de disponibilidad para venta:
      disponible_para_venta = stock_fisico - reservas_activas

    INV-27 (repunte de lectores): si se inyecta ``connection_provider``, la
    disponibilidad se lee de la proyección canónica (``inventory_balances``) vía
    ``CanonicalStockReadAdapter``, con la lectura legacy (reservas) como
    *fallback* mientras el stock se termina de sembrar. Sin ``connection_provider``
    el comportamiento es idéntico al legacy (retrocompatible por defecto).
    """

    def __init__(self, stock_reservation_service, *, connection_provider=None, env=None):
        self._reservations = stock_reservation_service
        self._adapter = None
        if connection_provider is not None:
            from core.services.inventory.canonical_stock_read_adapter import (
                CanonicalStockReadAdapter,
            )
            self._adapter = CanonicalStockReadAdapter(
                connection_provider,
                legacy_available=lambda p, b: self._legacy_available(p),
                env=env)

    def _legacy_available(self, producto_id) -> float:
        return float(self._reservations.stock_disponible(str(producto_id)))

    def disponible_para_venta(self, producto_id: int) -> float:
        if self._adapter is not None:
            return self._adapter.available_float(producto_id)
        return self._legacy_available(producto_id)

    def disponible_por_producto(self, producto_ids: Iterable[int]) -> Dict[int, float]:
        out: Dict[int, float] = {}
        for pid in producto_ids:
            out[int(pid)] = self.disponible_para_venta(int(pid))
        return out
