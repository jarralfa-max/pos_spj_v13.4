"""FASE SUP-9 (§52) — architecture guardrails for the supplier UI.

Suppliers live INSIDE Finanzas (no standalone menu), use query services + use
cases (no SQL/repos), the Design System (no inline styles/colors), the
specialized inputs (phone/tax/time), and never expose raw bank data.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUP_UI = REPO / "frontend" / "desktop" / "modules" / "finance" / "suppliers"

_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
_SETSTYLE = re.compile(r"\.setStyleSheet\s*\(\s*[^)\s]")
_SQL = re.compile(r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM)\b", re.IGNORECASE)


def _ui_files():
    return [p for p in SUP_UI.rglob("*.py") if "__pycache__" not in p.parts]


def test_supplier_ui_lives_inside_finance():
    assert SUP_UI.is_dir()
    assert (SUP_UI / "suppliers_view.py").exists()
    # registered as a Finanzas navigation page
    nav = (REPO / "frontend/desktop/modules/finance/finance_view.py").read_text(encoding="utf-8")
    assert "SuppliersPage" in nav and "Maestro de proveedores" in nav


def test_no_standalone_supplier_menu():
    """modulos/proveedores.py must delegate into Finanzas, never build its own UI."""
    src = (REPO / "modulos/proveedores.py").read_text(encoding="utf-8")
    assert "create_finance_view" in src and "proveedores" in src
    assert _SQL.search(src) is None
    assert len(src.splitlines()) < 30  # thin wrapper only


def test_supplier_ui_has_no_sql_or_repositories():
    offenders = []
    for path in _ui_files():
        text = path.read_text(encoding="utf-8")
        if _SQL.search(text) or "import sqlite3" in text \
                or "infrastructure.db.repositories" in text:
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"Supplier UI touches SQL/repositories: {offenders}"


def test_supplier_ui_has_no_inline_styles_or_hex():
    offenders = []
    for path in _ui_files():
        text = path.read_text(encoding="utf-8")
        if _SETSTYLE.search(text) or _HEX.search(text):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"Supplier UI has inline styles/hex colors: {offenders}"


def test_supplier_forms_use_specialized_inputs():
    dialogs = (SUP_UI / "dialogs" / "supplier_dialogs.py").read_text(encoding="utf-8")
    for widget in ("TaxIdentifierInput", "PhoneInput", "EmailInput", "MoneyInput",
                   "PercentInput", "TimeRangeInput", "SearchableComboBox"):
        assert widget in dialogs, f"supplier form must use {widget}"
    # RFC/phone must not be captured with a raw QLineEdit (instantiation/import)
    assert "QLineEdit(" not in dialogs
    assert "import QLineEdit" not in dialogs and " QLineEdit," not in dialogs


def test_supplier_ui_delegates_to_presenter_only():
    """Pages import the presenter/components, not backend use cases/queries directly."""
    for name in ("pages/supplier_list_page.py", "pages/supplier_detail_dialog.py"):
        text = (SUP_UI / name).read_text(encoding="utf-8")
        assert "backend.application.suppliers.use_cases" not in text
        assert "backend.application.suppliers.queries" not in text
