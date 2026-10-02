"""Cuánto vale devolver una línea y por dónde se regresa el dinero (§43-44).

DOS REGLAS DE DOMINIO, decididas por el usuario el 2026-10-02:

1. **Importe neto de la línea.** Lo que el cliente PAGÓ por una línea es su
   `line_total` MENOS su parte del descuento a nivel venta y del canje de
   puntos (que no viven en ninguna línea). Antes el reembolso salía de
   `line_total` a secas: con un 10 % a toda la venta, devolver todo
   reembolsaba $220 por una venta que cobró $198. El reparto es proporcional al
   `line_total` y se ajusta al centavo por residuo mayor, de modo que la suma de
   los netos de las líneas es EXACTAMENTE el total cobrado.

2. **Por dónde sale el reembolso: "método original, efectivo primero".** Se
   regresa primero lo pagado en efectivo (neto del cambio entregado), y lo que
   exceda va a los demás métodos en el orden en que se pagaron; lo pagado a
   crédito se reembolsa bajando la deuda. El reparto es ACUMULATIVO entre
   devoluciones de la misma venta: se reparte lo devuelto hasta ahora más lo
   nuevo y se descuenta lo que ya se había repartido, así varias devoluciones
   parciales nunca reembolsan dos veces el mismo efectivo.

Puro: sin E/S; sólo Decimal.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Iterable, Sequence

_CENT = Decimal("0.01")


def line_net_values(lines: Sequence, *, total: Decimal) -> dict[str, Decimal]:
    """Neto pagado por cada línea (id → importe), sumando exactamente `total`."""
    base = sum((line.line_total for line in lines), Decimal("0"))
    if not lines:
        return {}
    if base <= 0:
        return {line.id: Decimal("0") for line in lines}
    total = Decimal(str(total))
    crudos = {line.id: line.line_total * total / base for line in lines}
    netos = {lid: valor.quantize(_CENT, rounding=ROUND_DOWN) for lid, valor in crudos.items()}
    faltan = int(((total.quantize(_CENT) - sum(netos.values())) / _CENT).to_integral_value())
    por_residuo = sorted(crudos, key=lambda lid: crudos[lid] - netos[lid], reverse=True)
    for lid in por_residuo[:max(faltan, 0)]:
        netos[lid] += _CENT
    return netos


def return_amount(*, line_net: Decimal, line_quantity: Decimal, already_returned_quantity: Decimal,
                  already_returned_amount: Decimal, quantity: Decimal) -> Decimal:
    """Importe de devolver `quantity` de una línea. Si con esto la línea queda
    devuelta por completo, es lo que FALTA de su neto (sin residuos de
    redondeo acumulados entre devoluciones)."""
    if already_returned_quantity + quantity >= line_quantity:
        return max(line_net - already_returned_amount, Decimal("0"))
    return (line_net * quantity / line_quantity).quantize(_CENT)


def net_payments(payments: Iterable, *, change: Decimal) -> list[tuple[str, Decimal]]:
    """[(método, neto)] en orden de reembolso: efectivo (neto del cambio)
    primero; los demás en el orden en que se registraron."""
    totales: dict[str, Decimal] = {}
    orden: list[str] = []
    for payment in payments:
        metodo = getattr(payment.method, "value", payment.method)
        if metodo not in totales:
            totales[metodo] = Decimal("0")
            orden.append(metodo)
        totales[metodo] += payment.amount
    if "CASH" in totales:
        totales["CASH"] = max(totales["CASH"] - Decimal(str(change)), Decimal("0"))
        orden.remove("CASH")
        orden.insert(0, "CASH")
    return [(metodo, totales[metodo]) for metodo in orden if totales[metodo] > 0]


def _fill(payments: Sequence[tuple[str, Decimal]], amount: Decimal) -> dict[str, Decimal]:
    resto, reparto = Decimal(str(amount)), {}
    for metodo, disponible in payments:
        if resto <= 0:
            break
        tomar = min(resto, disponible)
        reparto[metodo] = reparto.get(metodo, Decimal("0")) + tomar
        resto -= tomar
    return reparto


def allocate_refund(payments: Sequence[tuple[str, Decimal]], *, already_refunded: Decimal,
                    amount: Decimal) -> list[tuple[str, Decimal]]:
    """Cómo se reembolsa `amount` dado lo ya reembolsado de la venta."""
    antes = _fill(payments, already_refunded)
    despues = _fill(payments, Decimal(str(already_refunded)) + Decimal(str(amount)))
    return [(metodo, despues[metodo] - antes.get(metodo, Decimal("0")))
            for metodo, _ in payments
            if despues.get(metodo, Decimal("0")) - antes.get(metodo, Decimal("0")) > 0]
