"""Unit tests for delivery quantity formatting across all 7 unit codes,
plus guard against silent 'kg' fallbacks in the delivery backend.

Covers Phase 5 / Phase 16 (tests 1-8) of SPJ_REFACTOR_SKILL audit.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from core.delivery.application.quantity_formatter import QuantityFormatter
from core.delivery.domain.value_objects import UnitCode, UNIT_LABELS_ES, WEIGHABLE_UNITS


# ── 1-7. Each unit code formats with its real label, never hardcoded ─────────

def test_format_kilogram():
    out = QuantityFormatter.format(Decimal("0.750"), UnitCode.KILOGRAM)
    assert out == "0.75 kg"


def test_format_gram():
    out = QuantityFormatter.format(Decimal("250"), UnitCode.GRAM)
    assert out.endswith(UNIT_LABELS_ES[UnitCode.GRAM])
    assert "250" in out


def test_format_piece():
    out = QuantityFormatter.format(Decimal("3"), UnitCode.PIECE)
    assert out == f"3 {UNIT_LABELS_ES[UnitCode.PIECE]}"


def test_format_unit():
    out = QuantityFormatter.format(Decimal("5"), UnitCode.UNIT)
    assert out == f"5 {UNIT_LABELS_ES[UnitCode.UNIT]}"


def test_format_box():
    out = QuantityFormatter.format(Decimal("2"), UnitCode.BOX)
    assert out == f"2 {UNIT_LABELS_ES[UnitCode.BOX]}"


def test_format_pack():
    out = QuantityFormatter.format(Decimal("4"), UnitCode.PACK)
    assert out == f"4 {UNIT_LABELS_ES[UnitCode.PACK]}"


def test_format_liter():
    out = QuantityFormatter.format(Decimal("1.5"), UnitCode.LITER)
    assert out == f"1.5 {UNIT_LABELS_ES[UnitCode.LITER]}"


# ── Weighable vs countable behaviour ─────────────────────────────────────────

def test_weighable_strips_trailing_zeros():
    assert QuantityFormatter.format(Decimal("1.000"), UnitCode.KILOGRAM) == "1 kg"


def test_countable_whole_renders_integer():
    out = QuantityFormatter.format(Decimal("3.0"), UnitCode.PIECE)
    assert out.startswith("3 ")


def test_every_unit_code_has_label():
    for unit in UnitCode:
        assert unit in UNIT_LABELS_ES, f"missing label for {unit}"


def test_weighable_set_contains_kg_g_liter():
    assert UnitCode.KILOGRAM in WEIGHABLE_UNITS
    assert UnitCode.GRAM in WEIGHABLE_UNITS
    assert UnitCode.LITER in WEIGHABLE_UNITS


# ── 8. No silent 'kg' default fallback in delivery backend ───────────────────

_ROOT = Path(__file__).parent.parent


@pytest.mark.parametrize(
    "rel_path",
    [
        "core/delivery/domain/entities.py",
        "core/delivery/application/adjust_delivery_weight.py",
        "core/services/delivery_service.py",
    ],
)
def test_no_silent_kg_default_in_backend(rel_path):
    """These modules must not default a unit param/field to 'kg'.

    The unit must always come from the frozen order item, never a silent
    fallback (SPJ_REFACTOR_SKILL Phase 5).
    """
    src = (_ROOT / rel_path).read_text(encoding="utf-8")
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Match `= "kg"` or `or "kg"` default fallbacks
        if '"kg"' in line or "'kg'" in line:
            raise AssertionError(
                f"Silent 'kg' fallback in {rel_path} line {lineno}:\n  {line.strip()}"
            )
