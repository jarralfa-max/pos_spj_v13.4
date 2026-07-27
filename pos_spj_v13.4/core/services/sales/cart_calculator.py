from __future__ import annotations

from typing import Any, Dict, List


class CartCalculator:
    """Single source of truth for cart totals/discounts/change preview."""

    @staticmethod
    def calculate(items: List[Dict[str, Any]], iva_rate: float = 0.0, global_discount: float = 0.0,
                  loyalty_discount: float = 0.0, amount_paid: float = 0.0) -> Dict[str, float]:
        precio_base = sum(float(it.get('cantidad', 0)) * float(it.get('precio_unitario', 0)) for it in items)
        subtotal_lineas = sum(float(it.get('total', 0.0)) for it in items)
        discount_lines = round(precio_base - subtotal_lineas, 2)

        subtotal = round(max(subtotal_lineas - float(global_discount or 0.0) - float(loyalty_discount or 0.0), 0.0), 2)
        impuestos = round(subtotal * float(iva_rate or 0.0), 2)
        total_final = round(subtotal + impuestos, 2)
        cambio = round(float(amount_paid or 0.0) - total_final, 2) if amount_paid else 0.0

        return {
            'precio_base': round(precio_base, 2),
            'descuento_lineas': discount_lines,
            'descuento_global': round(float(global_discount or 0.0), 2),
            'descuento_puntos': round(float(loyalty_discount or 0.0), 2),
            'subtotal': subtotal,
            'impuestos': impuestos,
            'total_final': total_final,
            'cambio': cambio,
            'puntos_preview': int(total_final),
        }
