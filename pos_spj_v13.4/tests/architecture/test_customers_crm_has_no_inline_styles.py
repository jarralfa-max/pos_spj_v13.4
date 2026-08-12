"""CRM-1 (§79, "Prohibido ... setStyleSheet en páginas") — no inline QSS in CRM UI.

Mirrors ``test_design_system_guardrails.py::test_no_inline_stylesheets_in_components``,
scoped to frontend/desktop/modules/customers_crm/ instead of components/.
"""

from __future__ import annotations

import re

from .customers_crm_guardrails import CRM_UI_ROOT, crm_ui_py_files, relative

_SETSTYLE_RE = re.compile(r"\.setStyleSheet\s*\(\s*[^)\s]")  # non-empty argument


def test_customers_crm_ui_has_no_inline_stylesheets():
    offenders = [relative(path) for path in crm_ui_py_files() if _SETSTYLE_RE.search(path.read_text(encoding="utf-8"))]
    assert not offenders, (
        f"Inline setStyleSheet() found under {relative(CRM_UI_ROOT)} — styling comes "
        f"from the theme layer/QSS, never inline: {offenders}"
    )
