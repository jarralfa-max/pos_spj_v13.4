# core/services/payment_normalization.py — SPJ ERP v13.4
"""
Normalización canónica de métodos de pago.

Convierte variantes de UI (con acentos, espacios, caps) a la forma
canónica esperada por los servicios backend.

Forma canónica → lo que SalesService, SaleFinanceHandler,
CreditSaleFinanceHandler y SaleInventoryHandler leen.

Uso:
    from core.services.payment_normalization import normalize_payment_method
    canonical = normalize_payment_method("Crédito")   # → "Credito"
    canonical = normalize_payment_method("Mercado Pago")  # → "Mercado Pago"
"""
from __future__ import annotations

_MAP: dict[str, str] = {
    # Efectivo
    "efectivo": "Efectivo",
    # Tarjeta
    "tarjeta": "Tarjeta",
    "tarjeta_credito": "Tarjeta",
    "tarjeta_debito": "Tarjeta",
    # Transferencia
    "transferencia": "Transferencia",
    "transfer": "Transferencia",
    "spei": "Transferencia",
    # Crédito cliente — normaliza acento / capitalización
    "credito": "Credito",
    "crédito": "Credito",
    "credito_cliente": "Credito",
    "credit": "Credito",
    # Pago mixto
    "pago mixto": "Pago Mixto",
    "pagomixto": "Pago Mixto",
    "mixto": "Pago Mixto",
    "mixed": "Pago Mixto",
    # MercadoPago
    "mercado pago": "Mercado Pago",
    "mercadopago": "Mercado Pago",
    "mp": "Mercado Pago",
    "mercadopago_qr": "Mercado Pago",
}


def normalize_payment_method(value: str) -> str:
    """
    Devuelve la forma canónica del método de pago.

    Si el valor ya es canónico o no está en la tabla, se devuelve
    tal cual (sin cambios) — conservador para no romper valores
    inesperados.

    Args:
        value: Cadena de método de pago, p.ej. "Crédito", "crédito",
               "Mercado Pago", "MercadoPago".

    Returns:
        Cadena canónica, p.ej. "Credito", "Mercado Pago".
    """
    if not value or not isinstance(value, str):
        return value or "Efectivo"
    return _MAP.get(value.strip().lower(), value.strip())


# Conjunto de formas de pago que se consideran "crédito al cliente".
CREDIT_PAYMENT_METHODS: frozenset[str] = frozenset({"Credito", "Crédito", "credito", "crédito"})


def is_credit_sale(payment_method: str) -> bool:
    """Retorna True si el método de pago es crédito al cliente."""
    return normalize_payment_method(payment_method) == "Credito"


def is_mercado_pago(payment_method: str) -> bool:
    """Retorna True si el método de pago es Mercado Pago."""
    return normalize_payment_method(payment_method) == "Mercado Pago"


def is_deferred_payment(payment_method: str) -> bool:
    """
    Retorna True para pagos diferidos (aún no cobrados en caja/tesorería inmediata).
    Actualmente: Crédito y Mercado Pago.
    """
    canonical = normalize_payment_method(payment_method)
    return canonical in {"Credito", "Mercado Pago"}


def is_cash_like_payment(payment_method: str) -> bool:
    """Retorna True para pagos de cobro inmediato (no diferidos)."""
    return not is_deferred_payment(payment_method)
