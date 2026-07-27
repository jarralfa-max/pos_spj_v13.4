# application/dtos/sale_dto.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class SaleItemDTO:
    producto_id: int
    nombre: str
    cantidad: float
    precio_unitario: float
    descuento: float = 0.0
    unidad: str = "pza"
    subtotal: float = 0.0

    def __post_init__(self):
        if self.subtotal == 0.0:
            self.subtotal = round(self.cantidad * self.precio_unitario * (1 - self.descuento / 100), 2)

@dataclass
class CreateSaleDTO:
    items: List[SaleItemDTO]
    cliente_id: Optional[int] = None
    sucursal_id: int = 1
    forma_pago: str = "Efectivo"
    descuento_global: float = 0.0
    efectivo_recibido: float = 0.0
    notas: str = ""
    usuario: str = ""

@dataclass
class SaleResultDTO:
    ok: bool
    venta_id: int = 0
    folio: str = ""
    total: float = 0.0
    cambio: float = 0.0
    error: str = ""
