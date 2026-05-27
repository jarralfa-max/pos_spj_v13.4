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
        data = {
            "forma_pago": m,
            "total_pagado": float(total or 0.0),
            "efectivo_recibido": float(amount_paid or 0.0),
            "monto_tarjeta_mixto": 0.0,
            "cambio": 0.0,
            "saldo_credito": 0.0,
        }
        if m == "Pago Mixto":
            data["efectivo_recibido"] = float(cash or 0.0)
            data["monto_tarjeta_mixto"] = float(card or 0.0)
            v = PaymentPolicy.validate_mixed_payment(total, cash, card)
            data["cambio"] = max(v["diff"], 0.0)
        elif m == "Crédito":
            data["saldo_credito"] = float(saldo_credito or total or 0.0)
            data["efectivo_recibido"] = float(total or 0.0)
        else:
            data["cambio"] = PaymentPolicy.calculate_change(total, amount_paid, m)
            if m != "Efectivo":
                data["efectivo_recibido"] = float(total or 0.0)
        return data
