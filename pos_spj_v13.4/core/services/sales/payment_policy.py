from __future__ import annotations

from typing import Any, Dict


class PaymentPolicy:
    @staticmethod
    def normalize_payment_method(method: str) -> str:
        raw = (method or "").strip().lower()
        mapping = {
            "efectivo": "Efectivo",
            "tarjeta": "Tarjeta",
            "transferencia": "Transferencia",
            "credito": "Crédito",
            "crédito": "Crédito",
            "pago mixto": "Pago Mixto",
            "mixto": "Pago Mixto",
            "mercado pago": "Mercado Pago",
            "mercadopago": "Mercado Pago",
        }
        return mapping.get(raw, method or "Efectivo")

    @staticmethod
    def is_credit_sale(method: str) -> bool:
        return PaymentPolicy.normalize_payment_method(method) == "Crédito"

    @staticmethod
    def is_pending_payment(method: str) -> bool:
        return PaymentPolicy.normalize_payment_method(method) == "Mercado Pago"

    @staticmethod
    def calculate_change(total: float, amount_paid: float, method: str) -> float:
        m = PaymentPolicy.normalize_payment_method(method)
        if m != "Efectivo":
            return 0.0
        return round(float(amount_paid or 0.0) - float(total or 0.0), 2)

    @staticmethod
    def validate_mixed_payment(total: float, cash: float, card: float) -> Dict[str, Any]:
        paid = round(float(cash or 0.0) + float(card or 0.0), 2)
        diff = round(paid - float(total or 0.0), 2)
        return {"ok": diff >= -0.01, "diff": diff, "paid": paid}

    @staticmethod
    def validate_payment(total: float, method: str, amount_paid: float = 0.0,
                         cash: float = 0.0, card: float = 0.0) -> Dict[str, Any]:
        m = PaymentPolicy.normalize_payment_method(method)
        if m == "Efectivo":
            ch = PaymentPolicy.calculate_change(total, amount_paid, m)
            return {"ok": ch >= 0, "change": ch, "error": "" if ch >= 0 else "Pago insuficiente"}
        if m == "Pago Mixto":
            v = PaymentPolicy.validate_mixed_payment(total, cash, card)
            return {"ok": v["ok"], "change": max(v["diff"], 0.0), "error": "" if v["ok"] else "Pago mixto insuficiente"}
        return {"ok": True, "change": 0.0, "error": ""}

    @staticmethod
    def build_payment_breakdown(total: float, method: str, amount_paid: float = 0.0,
                                cash: float = 0.0, card: float = 0.0,
                                saldo_credito: float = 0.0) -> Dict[str, Any]:
        m = PaymentPolicy.normalize_payment_method(method)
        total = round(float(total or 0.0), 2)
        amount_paid = round(float(amount_paid or 0.0), 2)
        lineas = {
            "efectivo": 0.0,
            "tarjeta": 0.0,
            "transferencia": 0.0,
            "credito": 0.0,
            "mercado_pago": 0.0,
        }
        cambio = 0.0
        amount_paid_real = 0.0

        if m == "Efectivo":
            lineas["efectivo"] = amount_paid
            amount_paid_real = amount_paid
            cambio = PaymentPolicy.calculate_change(total, amount_paid, m)
        elif m == "Tarjeta":
            lineas["tarjeta"] = total
            amount_paid_real = total
        elif m == "Transferencia":
            lineas["transferencia"] = total
            amount_paid_real = total
        elif m == "Mercado Pago":
            lineas["mercado_pago"] = total
            amount_paid_real = total
        elif m == "Crédito":
            lineas["credito"] = float(saldo_credito or total or 0.0)
            amount_paid_real = 0.0
        elif m == "Pago Mixto":
            lineas["efectivo"] = round(float(cash or 0.0), 2)
            lineas["tarjeta"] = round(float(card or 0.0), 2)
            v = PaymentPolicy.validate_mixed_payment(total, cash, card)
            cambio = max(float(v.get("diff", 0.0)), 0.0)
            amount_paid_real = round(lineas["efectivo"] + lineas["tarjeta"], 2)
        else:
            raise ValueError(f"Método de pago desconocido: {method}")

        return {
            "forma_pago": m,
            "total_pagado": amount_paid_real,
            "amount_paid": amount_paid_real,
            "amount_paid_real": amount_paid_real,
            "efectivo_recibido": lineas["efectivo"],
            "monto_tarjeta_mixto": lineas["tarjeta"],
            "tarjeta": lineas["tarjeta"],
            "transferencia": lineas["transferencia"],
            "credito": lineas["credito"],
            "mercado_pago": lineas["mercado_pago"],
            "cambio": cambio,
            "saldo_credito": lineas["credito"],
            "lineas": lineas,
            "breakdown": lineas,
        }
