# backend/application/services/cash_count_service.py
"""
CashCountService — cálculo puro del arqueo de caja (conteo por denominaciones).

Lógica extraída de la UI (modulos/caja.py) para que el Corte Z ciego no
dependa de widgets PyQt. La UI solo captura cantidades y renderiza los
subtotales que este servicio calcula.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Tuple


def compute_denomination_subtotals(
    denominations: Iterable[Tuple[str, float]],
    counts: Mapping[float, int],
) -> tuple[dict[float, float], float]:
    """
    Calcula subtotal por denominación y total contado.

    Args:
        denominations: secuencia de (etiqueta, valor) — p. ej. ("$500", 500).
        counts: mapa valor → piezas contadas.

    Returns:
        (subtotales_por_valor, total_contado) con total redondeado a 2 decimales.
    """
    subtotals: dict[float, float] = {}
    total = 0.0
    for _label, valor in denominations:
        piezas = int(counts.get(valor, 0) or 0)
        sub = round(float(valor) * piezas, 2)
        subtotals[valor] = sub
        total += sub
    return subtotals, round(total, 2)


def compute_cash_difference(expected_cash: float, counted_cash: float) -> float:
    """
    Diferencia del corte: efectivo contado contra efectivo ESPERADO.

    El efectivo esperado excluye pagos con tarjeta, transferencia y crédito;
    esos medios no pueden compararse contra el efectivo físico contado.
    """
    return round(float(counted_cash or 0.0) - float(expected_cash or 0.0), 2)
