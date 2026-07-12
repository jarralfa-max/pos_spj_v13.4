# tests/architecture/test_remediacion_a_trace_cleanup.py
"""Remediación A — limpieza de la traza financiera 083 (DEEP_AUDIT B3).

La traza 083 suscribía 10 handlers, 6 de ellos a canales lowercase que NADIE
emite en el repo. Esta limpieza:
  - reconecta waste → MERMA_REGISTRADA y driver-settlement → DRIVER_SETTLEMENT_CREATED
    (canales con emisor real),
  - retira las 4 suscripciones sin emisor (payment_confirmed,
    delivery_payment_confirmed, maintenance_registered, operating_supply_purchased).

Los tests son estáticos (AST/regex sobre el wiring) para bloquear la regresión.
"""
from __future__ import annotations

import ast
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[2]
WIRING = PKG_ROOT / "core" / "events" / "wiring.py"


def _trace_fn_source() -> str:
    src = WIRING.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_wire_financial_trace_handlers":
            return ast.get_source_segment(src, node) or ""
    raise AssertionError("no se encontró _wire_financial_trace_handlers")


_DEAD_CHANNELS = (
    "PAYMENT_CONFIRMED",
    "DELIVERY_PAYMENT_CONFIRMED",
    "MAINTENANCE_REGISTERED",
    "OPERATING_SUPPLY_PURCHASED",
    "WASTE_RECORDED",
)


def test_no_subscribe_a_canales_muertos():
    body = _trace_fn_source()
    for ch in _DEAD_CHANNELS:
        # No debe existir una suscripción a estos nombres muertos.
        assert f"bus.subscribe({ch}" not in body.replace(" ", ""), (
            f"B3: la traza 083 sigue suscrita al canal sin emisor {ch}."
        )


def test_waste_trace_usa_canal_real():
    body = _trace_fn_source()
    assert "MERMA_CREATED" in body and "WasteTraceHandler" in body, (
        "B3: WasteTraceHandler debe suscribirse a MERMA_CREATED (=MERMA_REGISTRADA)."
    )


def test_driver_settlement_trace_usa_canal_uppercase_real():
    body = _trace_fn_source()
    # DRIVER_SETTLEMENT_CREATED debe importarse desde event_bus (uppercase real),
    # no desde domain_events (lowercase sin emisor).
    assert "from core.events.event_bus import" in body
    assert "DRIVER_SETTLEMENT_CREATED" in body and "DriverSettlementHandler" in body


def test_canales_sanos_se_conservan():
    body = _trace_fn_source()
    for ch in ("VENTA_COMPLETADA", "COMPRA_REGISTRADA", "PAYROLL_PAID", "PUNTOS_ACUMULADOS"):
        assert ch in body, f"B3: se perdió la traza sana {ch}."
