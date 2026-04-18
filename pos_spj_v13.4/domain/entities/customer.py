# domain/entities/customer.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class Customer:
    id: int
    nombre: str
    telefono: str = ""
    email: str = ""
    direccion: str = ""
    activo: bool = True
    credit_limit: float = 0.0
    credit_balance: float = 0.0
    puntos: int = 0

    @property
    def credito_disponible(self) -> float:
        return max(0.0, self.credit_limit - self.credit_balance)

    def tiene_credito_suficiente(self, monto: float) -> bool:
        return self.credito_disponible >= monto
