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
    assert (PUR_UI / "pages" / "direct_purchase_create_page.py").exists()
    assert (PUR_UI / "pages" / "direct_purchase_history_page.py").exists()


def test_entry_wrapper_is_thin_and_sql_free():
    assert not (REPO / "modulos/compra_directa.py").exists()
    shell = (PUR_UI / "purchasing_module_shell.py").read_text(encoding="utf-8")
    navigation = (PUR_UI / "navigation.py").read_text(encoding="utf-8")
    assert "PurchasingRoutes.DIRECT_PURCHASE_CREATE" in shell
    assert "PurchasingRoutes.DIRECT_PURCHASE_HISTORY" in shell
    assert '"Nueva compra"' in navigation and '"Historial"' in navigation


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
    for name in ("direct_purchase_create_page.py", "direct_purchase_history_page.py"):
        text = (PUR_UI / "pages" / name).read_text(encoding="utf-8")
        assert "backend.application.procurement.use_cases" not in text
        assert "backend.application.procurement.queries" not in text
        assert "ProcurementUnitOfWork" not in text


def test_page_does_not_do_money_math_or_offer_pos_cash():
    text = (PUR_UI / "pages" / "direct_purchase_create_page.py").read_text(encoding="utf-8")
    # totals come from the presenter, not summed in the widget
    assert "self._presenter.totals(" in text
    assert "Reversar" not in text
    assert "QSplitter" in text and "setStretchFactor(0, 7)" in text
    assert "PurchaseProcessStepper" in text and "PurchaseSummaryPanel" in text
    assert "EntitySearchInput" in (PUR_UI / "dialogs" / "direct_purchase_dialogs.py").read_text(encoding="utf-8")
    # the widget never offers the POS operative cash as a payment source
    vms = (PUR_UI / "direct_purchase_view_models.py").read_text(encoding="utf-8")
    assert "POS_CASH" not in vms and "CAJA_POS" not in vms


def test_direct_purchase_presenter_has_no_fictitious_session_defaults():
    source = (PUR_UI / "direct_purchase_presenter.py").read_text(encoding="utf-8")
    assert 'else "desktop"' not in source
    assert 'or "MAIN"' not in source
    assert "warehouse_id\", None) or self.default_branch()" not in source


def test_purchasing_ui_does_not_write_permission_literals():
    offenders = []
    for path in _ui_files():
        source = path.read_text(encoding="utf-8")
        if ('.can("procurement.' in source or '.can("logistics.' in source
                or '.can("COMPRAS.' in source or '.can("LOGISTICA.' in source):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"Purchasing UI writes permission literals: {offenders}"


# ── PUR-12 enterprise UI + analytics ─────────────────────────────────────────
def test_enterprise_ui_exists_and_is_registered():
    assert (PUR_UI / "enterprise_view.py").exists()
    assert (PUR_UI / "pages" / "enterprise_pages.py").exists()
    assert (PUR_UI / "pages" / "procurement_dashboard_page.py").exists()
    wrapper = (REPO / "modulos/compras_enterprise.py").read_text(encoding="utf-8")
    assert "create_enterprise_purchasing_view" in wrapper
    loader = (REPO / "core/ui/module_loader.py").read_text(encoding="utf-8")
    assert "compras_enterprise" in loader


def test_analytics_dtos_are_color_free():
    """The analytics service must not embed colors/hex — only ChartDataDTO."""
    svc = (REPO / "backend/application/procurement/queries/"
           "procurement_analytics_service.py").read_text(encoding="utf-8")
    assert _HEX.search(svc) is None
    assert "setStyleSheet" not in svc


def test_enterprise_pages_delegate_to_presenter_only():
    for name in ("pages/enterprise_pages.py", "pages/procurement_dashboard_page.py"):
        text = (PUR_UI / name).read_text(encoding="utf-8")
        assert "backend.application.procurement.use_cases" not in text
        assert "backend.application.procurement.queries" not in text
        assert "ProcurementUnitOfWork" not in text
