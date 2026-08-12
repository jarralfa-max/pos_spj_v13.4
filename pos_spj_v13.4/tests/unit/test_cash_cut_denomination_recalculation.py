"""Arqueo de Corte Z: recalculo de subtotales por denominacion."""

from __future__ import annotations

from pathlib import Path

from backend.application.services.cash_count_service import (
    compute_cash_difference,
    compute_denomination_subtotals,
)


DENOMINACIONES = [
    ("$1000", 1000), ("$500", 500), ("$200", 200), ("$100", 100),
    ("$50", 50), ("$20", 20), ("$10", 10), ("$5", 5), ("$2", 2),
    ("$1", 1), ("$0.50", 0.5),
]


def test_subtotals_and_total():
    counts = {500: 2, 100: 3, 0.5: 4}
    subtotals, total = compute_denomination_subtotals(DENOMINACIONES, counts)
    assert subtotals[500] == 1000.0
    assert subtotals[100] == 300.0
    assert subtotals[0.5] == 2.0
    assert subtotals[1000] == 0.0
    assert total == 1302.0


def test_empty_counts_yield_zero():
    subtotals, total = compute_denomination_subtotals(DENOMINACIONES, {})
    assert total == 0.0
    assert all(value == 0.0 for value in subtotals.values())


def test_difference_compares_expected_vs_counted():
    assert compute_cash_difference(1500.00, 1480.50) == -19.50
    assert compute_cash_difference(1000.00, 1000.004) == 0.0
    assert compute_cash_difference(0, 250) == 250.0


def test_legacy_caja_ui_was_removed():
    assert not (Path(__file__).resolve().parents[2] / "modulos" / "caja.py").exists()
