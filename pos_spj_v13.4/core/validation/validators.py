
# core/validation/validators.py — SPJ POS v6.1
# Validadores centralizados — lógica de validación de dominio.
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional


class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field; self.message = message


class ProductValidator:
    @staticmethod
    def validate(data: Dict[str, Any]) -> None:
        nombre = str(data.get("nombre", "")).strip()
        if not nombre:
            raise ValidationError("nombre", "El nombre del producto es obligatorio")
        if len(nombre) > 200:
            raise ValidationError("nombre", "El nombre no puede exceder 200 caracteres")
        precio = float(data.get("precio", 0))
        if precio < 0:
            raise ValidationError("precio", "El precio no puede ser negativo")
        costo = float(data.get("costo", 0) or data.get("precio_compra", 0))
        if costo < 0:
            raise ValidationError("costo", "El costo no puede ser negativo")


class PriceValidator:
    @staticmethod
    def validate(precio: float, costo: float = 0, allow_zero: bool = False) -> None:
        if precio < 0:
            raise ValidationError("precio", "El precio no puede ser negativo")
        if not allow_zero and precio == 0:
            raise ValidationError("precio", "El precio no puede ser cero")
        if costo > 0 and precio > 0 and costo > precio * 2:
            raise ValidationError("precio", "El precio parece muy bajo respecto al costo")


class InventoryValidator:
    @staticmethod
    def validate_movement(cantidad: float, tipo: str) -> None:
        TIPOS = {"purchase","sale","adjustment","waste","production","return","transfer"}
        if tipo not in TIPOS:
            raise ValidationError("tipo", f"Tipo de movimiento inválido: {tipo}")
        if tipo == "waste" and cantidad < 0:
            raise ValidationError("cantidad", "La merma debe ser positiva")

    @staticmethod
    def validate_stock(disponible: float, requerido: float, producto: str = "") -> None:
        if requerido > disponible:
            from core.errors.error_handler import StockInsuficienteError
            raise StockInsuficienteError(producto, disponible, requerido)


class CustomerValidator:
    @staticmethod
    def validate(data: Dict[str, Any]) -> None:
        nombre = str(data.get("nombre", "")).strip()
        if not nombre:
            raise ValidationError("nombre", "El nombre del cliente es obligatorio")
        telefono = str(data.get("telefono", "") or "")
        if telefono and not re.match(r"^\+?[\d\s\-]{7,20}$", telefono):
            raise ValidationError("telefono", "Formato de teléfono inválido")
        email = str(data.get("email", "") or "")
        if email and "@" not in email:
            raise ValidationError("email", "Formato de email inválido")


class SaleValidator:
    @staticmethod
    def validate_items(items: list) -> None:
        if not items:
            raise ValidationError("items", "La venta no puede estar vacía")
        for item in items:
            if float(getattr(item, "cantidad", item.get("cantidad", 0) if isinstance(item, dict) else 0)) <= 0:
                raise ValidationError("cantidad", "La cantidad debe ser mayor a cero")
            if float(getattr(item, "precio_unitario", item.get("precio_unitario", 0) if isinstance(item, dict) else 0)) < 0:
                raise ValidationError("precio_unitario", "El precio no puede ser negativo")

    @staticmethod
    def validate_payment(total: float, pagado: float) -> None:
        if pagado < total - 0.01:
            raise ValidationError("pago", f"Pago insuficiente. Total: {total:.2f}, Pagado: {pagado:.2f}")
