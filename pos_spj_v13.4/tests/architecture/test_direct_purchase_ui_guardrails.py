"""PUR-5 — architecture guardrails for the direct-purchase UI.

The direct-purchase page lives in Compras (frontend/…/purchasing), uses the read
services + use cases through a presenter (no SQL/repos), the Design System (no
inline styles/colors) and the specialized inputs, and never lets the widget do
money math or decide the payment source. The POS never hosts it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PUR_UI = REPO / "frontend" / "desktop" / "modules" / "purchasing"

_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
_SETSTYLE = re.compile(r"\.setStyleSheet\s*\(\s*[^)\s]")
_SQL = re.compile(r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM)\b", re.IGNORECASE)


def _ui_files():
    return [p for p in PUR_UI.rglob("*.py") if "__pycache__" not in p.parts]


def test_direct_purchase_ui_exists_in_purchasing():
    assert PUR_UI.is_dir()
    assert (PUR_UI / "direct_purchase_view.py").exists()
    assert (PUR_UI / "pages" / "direct_purchase_page.py").exists()


def test_entry_wrapper_is_thin_and_sql_free():
    src = (REPO / "modulos/compra_directa.py").read_text(encoding="utf-8")
    assert "create_direct_purchase_view" in src
    assert _SQL.search(src) is None
    assert len(src.splitlines()) < 30


def test_direct_purchase_ui_has_no_sql_or_repositories():
    offenders = []
    for path in _ui_files():
        text = path.read_text(encoding="utf-8")
        if _SQL.search(text) or "import sqlite3" in text \
                or "infrastructure.db.repositories" in text:
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"Direct-purchase UI touches SQL/repositories: {offenders}"


def test_direct_purchase_ui_has_no_inline_styles_or_hex():
    offenders = []
    for path in _ui_files():
        text = path.read_text(encoding="utf-8")
        if _SETSTYLE.search(text) or _HEX.search(text):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"Direct-purchase UI has inline styles/hex: {offenders}"


def test_page_delegates_to_presenter_only():
    """The page imports the presenter/components, not backend use cases/queries."""
    text = (PUR_UI / "pages" / "direct_purchase_page.py").read_text(encoding="utf-8")
    assert "backend.application.procurement.use_cases" not in text
    assert "backend.application.procurement.queries" not in text
    assert "ProcurementUnitOfWork" not in text


def test_page_does_not_do_money_math_or_offer_pos_cash():
    text = (PUR_UI / "pages" / "direct_purchase_page.py").read_text(encoding="utf-8")
    # totals come from the presenter, not summed in the widget
    assert "self._presenter.totals(" in text
    # the widget never offers the POS operative cash as a payment source
    vms = (PUR_UI / "direct_purchase_view_models.py").read_text(encoding="utf-8")
    assert "POS_CASH" not in vms and "CAJA_POS" not in vms
