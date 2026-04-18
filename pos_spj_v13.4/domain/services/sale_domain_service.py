# domain/services/sale_domain_service.py
from __future__ import annotations
from typing import List
from domain.entities.sale import Sale, SaleItem

class SaleDomainService:
    def calcular_totales(self, items: List[SaleItem], descuento_global: float = 0.0) -> dict:
        subtotal = round(sum(i.subtotal for i in items), 2)
        descuento_monto = round(subtotal * descuento_global / 100, 2)
        total = round(subtotal - descuento_monto, 2)
        return {"subtotal": subtotal, "descuento_monto": descuento_monto, "total": total}

    def calcular_cambio(self, total: float, efectivo_recibido: float) -> float:
        return round(max(0.0, efectivo_recibido - total), 2)

    def validar_venta(self, sale: Sale) -> List[str]:
        return sale.validate()
