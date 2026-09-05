"""PROD-18 (§41, "No usar setStyleSheet en páginas") — no inline QSS in the
Products UI.

Mirrors `test_customers_crm_has_no_inline_styles.py`, scoped to
`frontend/desktop/modules/products/`. Confirmed clean by manual inspection
during the PROD-18 re-audit (2026-09-03) — this test makes that a ratchet.
"""

from __future__ import annotations

import re

from .products_ui_guardrails import PRODUCTS_UI_ROOT, products_ui_py_files, relative

_SETSTYLE_RE = re.compile(r"\.setStyleSheet\s*\(\s*[^)\s]")  # non-empty argument


def test_products_ui_has_no_inline_stylesheets():
    offenders = [relative(path) for path in products_ui_py_files()
                if _SETSTYLE_RE.search(path.read_text(encoding="utf-8"))]
    assert not offenders, (
        f"Inline setStyleSheet() found under {relative(PRODUCTS_UI_ROOT)} — styling "
        f"comes from the theme layer/QSS, never inline: {offenders}")
