"""PROD-18 (§41, "Los valores hexadecimales solo pueden vivir en themes") —
colors come from theme tokens only, never hardcoded in the Products UI.

Mirrors `test_customers_crm_has_no_hardcoded_colors.py`, scoped to
`frontend/desktop/modules/products/`. Confirmed clean by manual inspection
during the PROD-18 re-audit (2026-09-03) — this test makes that a ratchet
instead of a one-time observation, so a future regression is actually caught.
"""

from __future__ import annotations

import re

from .products_ui_guardrails import PRODUCTS_UI_ROOT, products_ui_py_files, relative

_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
_QCOLOR_RGB_RE = re.compile(r"QColor\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+")


def test_products_ui_has_no_hardcoded_hex_colors():
    offenders = []
    for path in products_ui_py_files():
        hits = _HEX_RE.findall(path.read_text(encoding="utf-8"))
        if hits:
            offenders.append(f"{relative(path)}: {hits[:5]}")
    assert not offenders, (
        f"Hardcoded hex colors under {relative(PRODUCTS_UI_ROOT)} (§41 — deben "
        f"vivir sólo en themes):\n" + "\n".join(offenders))


def test_products_ui_has_no_hardcoded_qcolor_rgb():
    offenders = []
    for path in products_ui_py_files():
        if _QCOLOR_RGB_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(relative(path))
    assert not offenders, (
        f"Hardcoded QColor(r,g,b) under {relative(PRODUCTS_UI_ROOT)}: {offenders}")
