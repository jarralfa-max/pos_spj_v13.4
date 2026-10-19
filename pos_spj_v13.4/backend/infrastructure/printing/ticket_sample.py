"""Datos de EJEMPLO para la vista previa y la impresión de prueba del diseñador
de tickets. Nunca datos reales de un cliente."""

from __future__ import annotations


def sample_payload(kind: str = "SALE") -> dict:
    if kind == "RAFFLE":
        return {"raffle_name": "Gran sorteo de aniversario", "ticket_number": "A-000123",
                "prize": "Pantalla de 55 pulgadas", "draw_date": "2026-12-20T18:00:00",
                "cliente": "Cliente de ejemplo", "sale_folio": "V-EJE-000001"}
    return {
        "folio": "V-EJE-000001", "fecha": "2026-10-16T12:30:00", "cajero": "Cajero de ejemplo",
        "cliente": "Cliente de ejemplo",
        "items": [
            {"nombre": "Pechuga de pollo", "unidad": "KG", "cantidad": 1.25,
             "precio_unitario": 115.0, "total": 143.75},
            {"nombre": "Alas", "unidad": "KG", "cantidad": 0.8, "precio_unitario": 75.0,
             "total": 60.0},
        ],
        "totales": {"subtotal": 203.75, "descuento": 0, "impuestos": 0, "total_final": 203.75},
        "pago": {"forma_pago": "CASH", "efectivo_recibido": 250.0, "cambio": 46.25},
        "loyalty": {"available": True, "puntos_totales": 340, "puntos_ganados": 20,
                    "nivel": "Oro"},
        "fomo_messages": ["Martes de 2x1 en alitas", "Junta 500 puntos y canjéalos aquí"],
    }
