# domain/entities/product.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class Product:
    id: int
    nombre: str
    precio: float
    existencia: float
    unidad: str = "pza"
    categoria: str = ""
    activo: bool = True
    oculto: bool = False
    stock_minimo: float = 0.0

    def tiene_stock(self, cantidad: float) -> bool:
        return self.existencia >= cantidad

    def esta_disponible(self) -> bool:
        return self.activo and not self.oculto
