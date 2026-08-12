"""CRM-1 (§79, "No colores hardcodeados") — colors come from theme tokens only.

Mirrors ``test_design_system_guardrails.py::test_no_hardcoded_hex_in_components``
(and its brand-hex check), scoped to the CRM UI module. No ``#RRGGBB`` literal
and no raw ``QColor(r, g, b)`` construction outside the theme layer.
"""

from __future__ import annotations

import re

from .customers_crm_guardrails import CRM_UI_ROOT, crm_ui_py_files, relative

_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
_QCOLOR_RGB_RE = re.compile(r"QColor\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+")


def test_customers_crm_ui_has_no_hardcoded_hex_colors():
    offenders = []
    for path in crm_ui_py_files():
        hits = _HEX_RE.findall(path.read_text(encoding="utf-8"))
        if hits:
            offenders.append(f"{relative(path)}: {hits[:5]}")
    assert not offenders, f"Hardcoded hex colors under {relative(CRM_UI_ROOT)}:\n" + "\n".join(offenders)


def test_customers_crm_ui_has_no_hardcoded_qcolor_rgb():
    offenders = []
    for path in crm_ui_py_files():
        if _QCOLOR_RGB_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(relative(path))
    assert not offenders, f"Hardcoded QColor(r,g,b) under {relative(CRM_UI_ROOT)}: {offenders}"
