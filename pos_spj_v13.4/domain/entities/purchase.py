# domain/entities/purchase.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class PurchaseItem:
    producto_id: int
    nombre: str
    cantidad: float
    costo_unitario: float
    unidad: str = "kg"

    @property
    def subtotal(self) -> float:
        return round(self.cantidad * self.costo_unitario, 2)

@dataclass
class Purchase:
    items: List[PurchaseItem]
    proveedor_id: int
    forma_pago: str = "CONTADO"
    monto_pagado: float = 0.0
    referencia_factura: str = ""
    notas: str = ""
    sucursal_id: int = 1

    @property
    def total(self) -> float:
        return round(sum(i.subtotal for i in self.items), 2)

    def validate(self) -> list[str]:
        errors = []
        if not self.items:
            errors.append("La compra debe tener al menos un producto")
        if self.proveedor_id <= 0:
            errors.append("Proveedor requerido")
        for item in self.items:
            if item.cantidad <= 0:
                errors.append(f"Cantidad inválida: {item.nombre}")
        return errors
