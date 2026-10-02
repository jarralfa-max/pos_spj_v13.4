"""SALE_COMPLETED (vocabulario de Ventas) → contrato de `SaleCompletedHandler`.

Ventas publica su evento con SUS términos: métodos de pago, totales de la
venta, cambio entregado. Finanzas espera los suyos: bruto/descuento/neto,
liquidaciones por tipo, costo de venta. La traducción vive aquí para que ningún
contexto aprenda el vocabulario del otro (mismo patrón que
`procurement/integrations/downstream_translators.py`).

Reglas de la traducción:

- neto = total de la venta; descuento = descuento + promoción + cupón + canje
  de puntos; bruto = neto + descuento. Así `bruto - descuento = neto`, que el
  manejador exige, y el ingreso (bruto - IVA) absorbe el redondeo.
- El efectivo se liquida NETO DEL CAMBIO: lo que queda en el cajón.
- El canje de puntos va como descuento, no contra el pasivo de puntos: la
  venta no identifica el instrumento canjeado y el manejador exige
  `instrument_id` para esa liquidación. Pendiente declarado.
"""

from __future__ import annotations

from decimal import Decimal

#: Método de pago del POS → tipo de liquidación de Finanzas.
SETTLEMENT_BY_METHOD = {
    "CASH": "CASH",
    "CARD": "CARD",
    "TRANSFER": "BANK_TRANSFER",
    "MERCADO_PAGO": "PAYMENT_PROCESSOR",
    "CREDIT": "ON_CREDIT",
}


def _dec(value) -> Decimal:
    return Decimal(str(value or "0"))


def sale_completed_to_finance(envelope: dict) -> dict:
    """Sobre de `sales_outbox` (`sale_event_payload`) → payload de Finanzas."""
    datos = dict(envelope.get("payload") or {})
    neto = _dec(datos.get("total"))
    descuento = sum((_dec(datos.get(k)) for k in (
        "discount_total", "promotion_total", "coupon_total", "loyalty_total")), Decimal("0"))
    cambio = _dec(datos.get("change"))

    liquidaciones: list[dict] = []
    for pago in datos.get("payments") or []:
        metodo = str(pago.get("method") or "")
        tipo = SETTLEMENT_BY_METHOD.get(metodo)
        if tipo is None:
            raise ValueError(f"Método de pago sin traducción a Finanzas: {metodo!r}")
        importe = _dec(pago.get("amount"))
        if tipo == "CASH":
            importe -= cambio
        if importe:
            liquidaciones.append({"type": tipo, "amount": str(importe)})

    return {
        "event_id": envelope.get("event_id"),
        "operation_id": envelope.get("operation_id"),
        "occurred_at": envelope.get("timestamp"),
        "branch_id": envelope.get("branch_id"),
        "sale_id": datos.get("sale_id") or envelope.get("entity_id"),
        "folio": datos.get("folio"),
        "customer_id": datos.get("customer_id"),
        "currency_code": datos.get("currency_code") or "MXN",
        "gross_total": str(neto + descuento),
        "discount_total": str(descuento),
        "net_total": str(neto),
        "tax_total": str(_dec(datos.get("tax_total"))),
        "settlements": liquidaciones,
        "cogs_total": str(_dec(datos.get("cogs_total"))),
    }


def sale_returned_to_finance(envelope: dict) -> dict:
    """SALE_RETURNED (devolución parcial) → payload de `SaleReturnedHandler`.

    Los reembolsos viajan por método de pago del POS y se traducen al mismo
    vocabulario de liquidación que la venta (`SETTLEMENT_BY_METHOD`)."""
    datos = dict(envelope.get("payload") or {})
    reembolsos = []
    for refund in datos.get("refunds") or []:
        metodo = str(refund.get("method") or "")
        tipo = SETTLEMENT_BY_METHOD.get(metodo)
        if tipo is None:
            raise ValueError(f"Método de reembolso sin traducción a Finanzas: {metodo!r}")
        reembolsos.append({"type": tipo, "amount": str(_dec(refund.get("amount")))})
    return {
        "event_id": envelope.get("event_id"),
        "operation_id": envelope.get("operation_id"),
        "occurred_at": envelope.get("timestamp"),
        "branch_id": envelope.get("branch_id"),
        "sale_id": envelope.get("entity_id"),
        "return_id": datos.get("return_id"),
        "folio": datos.get("folio"),
        "customer_id": datos.get("customer_id"),
        "currency_code": datos.get("currency_code") or "MXN",
        "amount": str(_dec(datos.get("amount"))),
        "gross_amount": str(_dec(datos.get("gross_amount") or datos.get("amount"))),
        "tax_amount": str(_dec(datos.get("tax_amount"))),
        "cogs_amount": str(_dec(datos.get("cogs_amount"))),
        "refunds": reembolsos,
    }


def sale_reversed_to_finance(envelope: dict) -> dict:
    """SALE_REVERSED → payload de `SaleReversedHandler` (revierte los asientos
    originales y cancela la CxC abierta)."""
    datos = dict(envelope.get("payload") or {})
    return {
        "event_id": envelope.get("event_id"),
        "operation_id": envelope.get("operation_id"),
        "occurred_at": envelope.get("timestamp"),
        "branch_id": envelope.get("branch_id"),
        "sale_id": envelope.get("entity_id"),
        "reason": datos.get("reason") or "Venta reversada",
    }
