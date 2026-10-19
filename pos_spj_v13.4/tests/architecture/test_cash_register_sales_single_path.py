"""Auditoría de Caja CJA-03 (2026-10-16): una sola vía Venta → Caja.

El mostrador registra Caja dentro de la transacción de la venta. Los manejadores
de evento de `sales_cash_handlers` existen (pruebas de CASH-9) pero suscribirlos
duplicaría el efectivo de cada venta."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_wiring_subscribes_the_sales_cash_handlers():
    offenders = []
    for folder in ("backend/application", "backend/bootstrap", "frontend"):
        for path in (ROOT / folder).rglob("*.py"):
            if path.name == "sales_cash_handlers.py":
                continue
            text = path.read_text(encoding="utf-8")
            if any(name in text for name in ("SaleCompletedCashHandler", "SaleCancelledCashHandler", "SaleRefundedCashHandler")):
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders
