# domain/entities/sale.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

@dataclass
class SaleItem:
    producto_id: int
    nombre: str
    cantidad: float
    precio_unitario: float
    descuento: float = 0.0
    unidad: str = "pza"

    @property
    def subtotal(self) -> float:
        return round((self.cantidad * self.precio_unitario) * (1 - self.descuento / 100), 2)

@dataclass
class Sale:
    items: List[SaleItem]
    cliente_id: Optional[int] = None
    sucursal_id: int = 1
    forma_pago: str = "Efectivo"
    descuento_global: float = 0.0
    notas: str = ""
    usuario: str = ""

    @property
    def subtotal(self) -> float:
        return round(sum(i.subtotal for i in self.items), 2)

    @property
    def total(self) -> float:
        return round(self.subtotal * (1 - self.descuento_global / 100), 2)

    def validate(self) -> list[str]:
        errors = []
        if not self.items:
            errors.append("La venta debe tener al menos un producto")
        for item in self.items:
            if item.cantidad <= 0:
                errors.append(f"Cantidad inválida para {item.nombre}")
            if item.precio_unitario < 0:
                errors.append(f"Precio inválido para {item.nombre}")
        return errors
